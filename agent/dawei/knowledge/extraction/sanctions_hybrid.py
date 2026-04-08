# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Hybrid sanctions extraction strategy — rule-based parsing + optional LLM fallback.

Strategy:
1. Detect data format (table vs free-text)
2. For structured data: use fast regex/template parsing
3. For unstructured data: delegate to LLM extractor
4. Merge results from both approaches

This avoids sending 94,000 LLM calls for data that is 90% structured lists.
"""

import json
import logging
import re
from typing import Any

from dawei.knowledge.extraction.base import (
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
    ExtractionStrategy,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for structured sanctions data
# ---------------------------------------------------------------------------

# a.k.a. / f.k.a. aliases
_RE_ALIAS_AKA = re.compile(r"a\.k\.a\.\s*['\"]?([^';\n]+?)['\"]?(?:\s*;\s*a\.k\.a\.\s*['\"]?([^';\n]+?)['\"]?)*", re.IGNORECASE)
_RE_ALIAS_FKA = re.compile(r"f\.k\.a\.\s*['\"]?([^';\n]+?)['\"]?(?:\s*;\s*f\.k\.a\.\s*['\"]?([^';\n]+?)['\"]?)*", re.IGNORECASE)

# Single alias extraction (handles multiple a.k.a./f.k.a. in sequence)
_RE_AKA_VALUES = re.compile(r"(?:a\.k\.a\.)\s*['\"]?([^';\n\"\)]+?)['\"]?(?:\s*;|\s*\)|\s*,\s*(?:a\.k\.a\.|f\.k\.a\.)|\s*$)", re.IGNORECASE)
_RE_FKA_VALUES = re.compile(r"(?:f\.k\.a\.)\s*['\"]?([^';\n\"\)]+?)['\"]?(?:\s*;|\s*\)|\s*,\s*(?:a\.k\.a\.|f\.k\.a\.)|\s*$)", re.IGNORECASE)

# Identifiers
_RE_TAX_ID = re.compile(r"Tax ID No[.\s]+(\S+)(?:\s*\((\w+)\))?", re.IGNORECASE)
_RE_REG_NUMBER = re.compile(r"(?:Registration|Reference)\s+Number\s+(\S+)(?:\s*\((\w+)\))?", re.IGNORECASE)
_RE_PASSPORT = re.compile(r"Passport\s+(\S+)(?:\s*\((\w+)\))?", re.IGNORECASE)
_RE_CEDULA = re.compile(r"Cedula No[.\s]+(\S+)(?:\s*\((\w+)\))?", re.IGNORECASE)
_RE_SSN = re.compile(r"SSN\s+(\d{3}-\d{2}-\d{4})(?:\s*\((\w+)\))?", re.IGNORECASE)
_RE_NATIONAL_ID = re.compile(r"National ID No[.\s]+(\S+)(?:\s*\((\w+)\))?", re.IGNORECASE)

# Dates
_RE_DOB = re.compile(r"DOB\s+(.*?)(?:;\s|$)", re.IGNORECASE)
_RE_POB = re.compile(r"POB\s+(.*?)(?:;\s|$)", re.IGNORECASE)
_RE_GENDER = re.compile(r"Gender\s+(Male|Female)", re.IGNORECASE)

# SWIFT/BIC
_RE_SWIFT = re.compile(r"SWIFT/BIC\s+(\w{8,11})", re.IGNORECASE)
_RE_IMO = re.compile(r"IMO\s+(\d{7})", re.IGNORECASE)
_RE_MMSI = re.compile(r"MMSI\s+(\d{9})", re.IGNORECASE)

# Vessel Registration Identification
_RE_VESSEL_REG = re.compile(r"Vessel Registration Identification\s+IMO\s+(\d{7})", re.IGNORECASE)

# Executive Order / Sanctions Program
_RE_EO = re.compile(r"Executive Order\s+(\d+)", re.IGNORECASE)
_RE_SANCTIONS_PROGRAM = re.compile(r"\[(\w[\w\s\-]*?)\]", re.IGNORECASE)

# Secondary sanctions risk
_RE_SECONDARY_RISK = re.compile(r"Secondary sanctions risk:\s*(.*?)(?:;\s|$)", re.IGNORECASE)

# Linked To
_RE_LINKED_TO = re.compile(r"Linked To:\s*(.*?)(?:;\s*$)", re.IGNORECASE)

# Additional Sanctions Information
_RE_ADDL_SANCTIONS = re.compile(r"Additional Sanctions Information\s*[-–]\s*(.*?)(?:;\s|$)", re.IGNORECASE)

# Company suffixes for type detection
_COMPANY_SUFFIXES = re.compile(
    r"\b(?:CO\.?\s*(?:LTD|INC)|LTD\.?|INC\.?|LLC|LLP|PLC|GMBH|S\.A\.|B\.V\.|AG|N\.V\.|SE|"
    r"JSC|OJSC|PJSC|CJSC|PAO|OAO|ZAO|公司|集团|股份有限公司|有限责任公司)\b",
    re.IGNORECASE,
)

# Government / public body keywords
_PUBLIC_BODY_KEYWORDS = re.compile(
    r"\b(?:MINISTRY|DEPARTMENT|AGENCY|AUTHORITY|COMMISSION|COUNCIL|DIRECTORATE|"
    r"OFFICE OF|ADMINISTRATION|BUREAU|GOVERNMENT|BANK\s+(?:OF|MARKAZI)|"
    r"财政部|商务部|委员会|办公室)\b",
    re.IGNORECASE,
)

# Vessel keywords
_VESSEL_KEYWORDS = re.compile(
    r"\b(?:VESSEL|SHIP|TANKER|CARRIER|CARGO|TUG|BULKER|FERRY)\b",
    re.IGNORECASE,
)

# --- Markdown table row parser ---
# Matches: | value1 | value2 | ... |
_MD_TABLE_ROW = re.compile(r"^\|(.+)\|$")

# Program codes (from SDN list)
_PROGRAM_CODES = {
    "SDGT", "SDNT", "SDNTK", "FTO", "NS-PLC", "SDT", "SDTET", "SRGE",
    "OFAC-SDN", "OFAC-BSL", "OFAC-PLC", "OFAC-SDT", "CYBER2", "CAATSA",
    "UKRAINE-EO13662", "UKRAINE-EO14024", "IRAN-IFSR", "IRAN-TRU",
    "IRGC", "IFSR", "IRAN-EO13902", "NPWMD", "PEESA", "PEESA-EO13883",
    "CAATSA-RUSSIA", "BELARUS", "BURMA", "CUBA", "IRAQ2", "DPRK",
    "DPRK2", "DPRK3", "SYRIA", "ZIMBABWE", "YEYMEN", "SOMALIA",
}


def _clean_name(name: str) -> str:
    """Clean entity name by stripping whitespace, quotes, trailing punctuation."""
    name = name.strip()
    name = name.strip("'\"")
    name = name.strip()
    # Remove trailing commas/semicolons
    while name and name[-1] in ",;.":
        name = name[:-1].strip()
    return name


def _detect_entity_type(name: str, row_type: str | None = None, extra_text: str = "") -> str:
    """Infer entity type from name, row type hint, and surrounding text."""
    upper = name.upper()

    # Direct type hint from table
    if row_type:
        rt = row_type.lower().strip()
        if "individual" in rt:
            return "Person"
        if "vessel" in rt:
            return "Vessel"
        if "aircraft" in rt or "airplane" in rt:
            return "Airplane"

    # Vessel keywords
    if _VESSEL_KEYWORDS.search(name) or _VESSEL_KEYWORDS.search(extra_text):
        return "Vessel"

    # Government / public body
    if _PUBLIC_BODY_KEYWORDS.search(name):
        return "PublicBody"

    # Company suffixes
    if _COMPANY_SUFFIXES.search(name):
        return "Company"

    # Heuristic: ALL CAPS with comma → likely Person ("LAST, First")
    # But many companies are also ALL CAPS
    # If name has comma and has lowercase after it → Person
    parts = name.split(",", 1)
    if len(parts) == 2:
        first_part = parts[0].strip()
        second_part = parts[1].strip()
        # If second part looks like given names (mixed case or short)
        if second_part and (second_part[0].isupper() or second_part[0].islower()):
            # Check it's not a company pattern like "CO, LTD"
            if not _COMPANY_SUFFIXES.search(second_part):
                return "Person"

    # Check for human-name patterns in extra text (DOB, POB, Gender)
    if _RE_DOB.search(extra_text) or _RE_GENDER.search(extra_text):
        return "Person"

    # Default: Company for organizations, check if it looks like a person name
    # Simple heuristic: 2-3 words, title case, no business words
    words = name.split()
    if len(words) == 2 and all(w[0].isupper() for w in words if w):
        # Could be person name like "ABDALLAH, Ramadan" (already handled above)
        # Or "COBALT REFINERY" → Company
        return "Company"

    return "Company"


def _extract_aliases(text: str) -> tuple[list[str], list[str]]:
    """Extract a.k.a. and f.k.a. aliases from text.

    Returns:
        (aka_list, fka_list)
    """
    akas = []
    fkas = []

    for m in _RE_AKA_VALUES.finditer(text):
        val = _clean_name(m.group(1))
        if val and len(val) > 1:
            akas.append(val)

    for m in _RE_FKA_VALUES.finditer(text):
        val = _clean_name(m.group(1))
        if val and len(val) > 1:
            fkas.append(val)

    return akas, fkas


def _extract_identifiers(text: str) -> dict[str, Any]:
    """Extract identifiers from sanctions text."""
    ids: dict[str, Any] = {}

    for m in _RE_TAX_ID.finditer(text):
        ids["taxNumber"] = m.group(1)
        if m.group(2):
            ids["taxNumberCountry"] = m.group(2)

    for m in _RE_REG_NUMBER.finditer(text):
        ids["registrationNumber"] = m.group(1)
        if m.group(2):
            ids["registrationNumberCountry"] = m.group(2)

    for m in _RE_PASSPORT.finditer(text):
        ids.setdefault("passportNumber", [])
        ids["passportNumber"].append({"number": m.group(1), "country": m.group(2) or ""})

    for m in _RE_CEDULA.finditer(text):
        ids.setdefault("idNumber", [])
        ids["idNumber"].append({"number": m.group(1), "country": m.group(2) or ""})

    for m in _RE_SSN.finditer(text):
        ids.setdefault("idNumber", [])
        ids["idNumber"].append({"number": m.group(1), "country": m.group(2) or "United States"})

    m = _RE_SWIFT.search(text)
    if m:
        ids["swiftBic"] = m.group(1)

    m = _RE_IMO.search(text)
    if m:
        ids["imoNumber"] = m.group(1)

    m = _RE_VESSEL_REG.search(text)
    if m and "imoNumber" not in ids:
        ids["imoNumber"] = m.group(1)

    m = _RE_MMSI.search(text)
    if m:
        ids["mmsi"] = m.group(1)

    return ids


def _extract_person_details(text: str) -> dict[str, Any]:
    """Extract person-specific details like DOB, POB, gender."""
    details: dict[str, Any] = {}

    m = _RE_DOB.search(text)
    if m:
        details["birthDate"] = m.group(1).strip().rstrip(";")

    m = _RE_POB.search(text)
    if m:
        details["birthPlace"] = m.group(1).strip().rstrip(";")

    m = _RE_GENDER.search(text)
    if m:
        details["gender"] = m.group(1)

    return details


def _extract_sanctions_info(text: str) -> dict[str, Any]:
    """Extract sanctions program, EO references, secondary risk info."""
    info: dict[str, Any] = {}

    # Executive Orders
    eos = [m.group(1) for m in _RE_EO.finditer(text)]
    if eos:
        info["executiveOrders"] = eos

    # Program codes from brackets
    programs = []
    for m in _RE_SANCTIONS_PROGRAM.finditer(text):
        code = m.group(1).strip().upper()
        if code in _PROGRAM_CODES or len(code) < 20:
            programs.append(code)
    if programs:
        info["programs"] = programs

    # Secondary sanctions risk
    m = _RE_SECONDARY_RISK.search(text)
    if m:
        info["secondaryRisk"] = m.group(1).strip()

    # Linked To
    linked = [m.group(1).strip() for m in _RE_LINKED_TO.finditer(text)]
    if linked:
        info["linkedTo"] = linked

    # Additional sanctions info
    m = _RE_ADDL_SANCTIONS.search(text)
    if m:
        info["additionalSanctionsInfo"] = m.group(1).strip()

    return info


def _has_structured_data(text: str) -> bool:
    """Detect if text contains structured sanctions data patterns."""
    # Check for common structured patterns
    indicators = [
        "a.k.a.",
        "f.k.a.",
        "DOB",
        "POB",
        "Executive Order",
        "Tax ID No",
        "Registration Number",
        "Passport",
        "SWIFT/BIC",
        "Secondary sanctions risk",
        "Linked To",
        "Vessel Registration Identification",
        "Gender Male",
        "Gender Female",
    ]
    count = sum(1 for pat in indicators if pat.lower() in text.lower())
    return count >= 2


def _parse_md_table_row(line: str) -> list[str] | None:
    """Parse a markdown table row into cells. Returns None if not a table row."""
    m = _MD_TABLE_ROW.match(line.strip())
    if not m:
        return None
    content = m.group(1)
    # Split by | but handle escaped pipes
    cells = [c.strip() for c in content.split("|")]
    return cells


def _extract_from_sdn_table(text: str, **kwargs) -> ExtractionResult:
    """Extract entities from SDN-style markdown table format.

    Table columns typically: index | id | name | type | country | ... | remarks
    """
    entities: list[ExtractedEntity] = []
    relations: list[ExtractedRelation] = []

    lines = text.split("\n")
    for line in lines:
        cells = _parse_md_table_row(line)
        if not cells or len(cells) < 4:
            continue

        # Skip header rows (cells contain mostly dashes or headers)
        non_empty = [c for c in cells if c and c != "-0-" and not all(ch in "-:" for ch in c)]
        if len(non_empty) < 2:
            continue

        # SDN table format: index | id | name | type | country | ... | remarks
        # Find the name cell (usually widest non-numeric content)
        name = ""
        row_type = ""
        country = ""
        remarks = ""

        # Typical column mapping (flexible):
        if len(cells) >= 5:
            # Try to find name (usually column index 2)
            for idx in [2, 1, 3]:
                if idx < len(cells):
                    candidate = cells[idx].strip()
                    if candidate and candidate != "-0-" and not candidate.isdigit():
                        name = candidate
                        break

            # Type column (usually index 3)
            if len(cells) > 3:
                row_type = cells[3].strip() if cells[3].strip() != "-0-" else ""

            # Country column (usually index 4)
            if len(cells) > 4:
                country = cells[4].strip() if cells[4].strip() != "-0-" else ""

            # Remarks (last column)
            if len(cells) > 10:
                remarks = cells[-1].strip() if cells[-1].strip() != "-0-" else ""

        if not name or len(name) < 2:
            continue

        # Combine remarks for alias/id extraction
        full_context = f"{name} {remarks}"

        # Detect entity type
        entity_type = _detect_entity_type(name, row_type, full_context)

        # Extract aliases
        akas, fkas = _extract_aliases(full_context)

        # Build properties
        properties: dict[str, Any] = {
            "source": "rule_based",
            "topics": ["sanction"],
        }
        if country:
            properties["country"] = country
        if akas:
            properties["alias"] = akas
        if fkas:
            properties["previousName"] = fkas

        # Extract identifiers
        ids = _extract_identifiers(full_context)
        properties.update(ids)

        # Person details
        if entity_type == "Person":
            person_details = _extract_person_details(full_context)
            properties.update(person_details)

        # Sanctions info
        sanctions_info = _extract_sanctions_info(full_context)
        if sanctions_info:
            properties.update(sanctions_info)

        entity_name = _clean_name(name)
        if not entity_name:
            continue

        entities.append(
            ExtractedEntity(
                name=entity_name,
                type=entity_type,
                properties=properties,
                confidence=0.9,
                mention_count=1,
            )
        )

    return ExtractionResult(entities=entities, relations=relations)


def _extract_from_free_text(text: str, **kwargs) -> ExtractionResult:
    """Extract entities from free-text sanctions data (e.g., MBS list, OFAC prose format).

    Handles patterns like:
    - "ENTITY NAME (a.k.a. X; f.k.a. Y), Address, Country; Registration Number N"
    - "TRANSPORTU NEFTI TRANSNEFT PAO (f.k.a. AK TRANSNEFT OAO; a.k.a. JSC TRANSNEFT)"
    """
    entities: list[ExtractedEntity] = []
    relations: list[ExtractedRelation] = []

    # Strategy: split by common delimiters that separate entity entries
    # OFAC lists often use newlines or form feeds between entries
    # Try to find entity blocks

    # Extract structured identifiers first (cross-reference later)
    ids = _extract_identifiers(text)
    akas, fkas = _extract_aliases(text)
    person_details = _extract_person_details(text)
    sanctions_info = _extract_sanctions_info(text)

    # Try to find the primary entity name
    # In OFAC format, the name is typically at the start before a.k.a./f.k.a./address
    # Pattern: UPPERCASE NAME (possibly with commas) followed by aliases or details

    # Method 1: Look for names followed by aliases
    # "NAME (a.k.a. X)" or "NAME, a.k.a. X"
    _RE_ENTITY_WITH_ALIAS = re.compile(
        r"([A-Z][A-Z\s\.\-,/']{3,100}?)"
        r"\s*[\(\[,;]\s*"
        r"(?:a\.k\.a\.|f\.k\.a\.)",
        re.IGNORECASE,
    )

    # Method 2: Names followed by Registration/ID numbers
    _RE_ENTITY_WITH_ID = re.compile(
        r"([A-Z][A-Z\s\.\-,/']{3,100}?)"
        r"\s*[\(\[,;]\s*"
        r"(?:Number|Registration|Tax ID)",
        re.IGNORECASE,
    )

    found_names: set[str] = set()

    for pattern in [_RE_ENTITY_WITH_ALIAS, _RE_ENTITY_WITH_ID]:
        for m in pattern.finditer(text):
            name = _clean_name(m.group(1))
            if name and len(name) > 2 and name not in found_names:
                # Skip common non-entity patterns
                skip_words = {"OFFICE OF", "DEPARTMENT", "FOREIGN ASSETS", "SANCTIONS LIST", "ADDITIONAL"}
                if any(sw in name.upper() for sw in skip_words):
                    continue
                found_names.add(name)

    # If no structured names found, try to find any capitalized entity names
    if not found_names:
        # Look for consecutive lines of uppercase text (common in OFAC lists)
        _RE_CAPS_NAME = re.compile(r"^([A-Z][A-Z\s\.\-/,']{5,80}?)[\s]*$", re.MULTILINE)
        for m in _RE_CAPS_NAME.finditer(text):
            name = _clean_name(m.group(1))
            if name and len(name) > 3 and name not in found_names:
                skip_words = {"OFFICE", "DEPARTMENT", "FOREIGN", "CONTROL", "SANCTIONS", "TREASURY", "LIST"}
                if not any(name.upper().startswith(sw) for sw in skip_words):
                    found_names.add(name)

    for name in found_names:
        entity_type = _detect_entity_type(name, extra_text=text)

        properties: dict[str, Any] = {
            "source": "rule_based",
            "topics": ["sanction"],
        }
        if akas:
            properties["alias"] = akas
        if fkas:
            properties["previousName"] = fkas
        properties.update(ids)
        if entity_type == "Person":
            properties.update(person_details)
        properties.update(sanctions_info)

        entities.append(
            ExtractedEntity(
                name=name,
                type=entity_type,
                properties=properties,
                confidence=0.85,
                mention_count=1,
            )
        )

    return ExtractionResult(entities=entities, relations=relations)


class SanctionsHybridExtractor(ExtractionStrategy):
    """Hybrid sanctions extraction: rule-based for structured data, LLM fallback for complex text.

    Strategy:
    1. Try fast rule-based parsing (table + free-text patterns)
    2. If results are sparse (< threshold), optionally call LLM for more
    3. Merge both results

    Config:
        llm_fallback: bool — whether to fall back to LLM for sparse results (default: False)
        llm_config_name: str — LLM config name for fallback
        min_entities_threshold: int — if rule-based yields fewer, trigger LLM (default: 0)
        max_text_length: int — max chars per LLM call (default: 4000)
    """

    strategy_name = "sanctions_hybrid"

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.llm_fallback = self.config.get("llm_fallback", False)
        self.llm_config_name = self.config.get("llm_config_name")
        self.min_entities_threshold = self.config.get("min_entities_threshold", 0)
        self.max_text_length = self.config.get("max_text_length", 4000)
        self._llm_extractor = None

    async def extract(self, text: str, **kwargs) -> ExtractionResult:
        """Extract entities using hybrid approach."""
        # Step 1: Rule-based extraction
        result = self._rule_based_extract(text, **kwargs)

        # Step 2: LLM fallback if results are sparse
        if self.llm_fallback and len(result.entities) <= self.min_entities_threshold:
            logger.debug(
                f"Rule-based extracted {len(result.entities)} entities (threshold: {self.min_entities_threshold}), "
                f"falling back to LLM"
            )
            llm_result = await self._llm_extract(text, **kwargs)
            if llm_result:
                # Merge: rule-based entities take priority (higher confidence)
                result = self._merge_with_priority(result, llm_result)

        # Attach source provenance
        chunk_id = kwargs.get("chunk_id")
        document_id = kwargs.get("document_id")
        page_number = kwargs.get("page_number")

        for entity in result.entities:
            if not entity.source_chunk_id and chunk_id:
                entity.source_chunk_id = chunk_id
            if not entity.source_document_id and document_id:
                entity.source_document_id = document_id
            if entity.source_page_number is None and page_number is not None:
                entity.source_page_number = page_number

        return result

    def _rule_based_extract(self, text: str, **kwargs) -> ExtractionResult:
        """Run rule-based extraction with format detection."""
        # Detect format
        has_table = bool(_MD_TABLE_ROW.match(text.strip().split("\n")[0]) if text.strip() else False)
        has_structure = _has_structured_data(text)

        if has_table:
            return _extract_from_sdn_table(text, **kwargs)
        elif has_structure:
            return _extract_from_free_text(text, **kwargs)
        else:
            # Try both and take the better result
            table_result = _extract_from_sdn_table(text, **kwargs)
            text_result = _extract_from_free_text(text, **kwargs)

            if len(table_result.entities) >= len(text_result.entities):
                return table_result
            return text_result

    async def _llm_extract(self, text: str, **kwargs) -> ExtractionResult | None:
        """Delegate to LLM extractor for complex text."""
        try:
            if self._llm_extractor is None:
                from dawei.knowledge.extraction.llm_extractor import LLMExtractor

                llm_config = {}
                if self.llm_config_name:
                    llm_config["llm_config_name"] = self.llm_config_name

                # Inject domain profile
                from dawei.knowledge.domains.registry import DomainRegistry

                profile = DomainRegistry.get("sanctions")
                if profile:
                    llm_config["domain_profile"] = profile

                self._llm_extractor = LLMExtractor(config=llm_config)

            return await self._llm_extractor.extract(text, **kwargs)
        except Exception as e:
            logger.warning(f"LLM fallback extraction failed: {e}")
            return None

    def _merge_with_priority(self, primary: ExtractionResult, secondary: ExtractionResult) -> ExtractionResult:
        """Merge two results, primary takes priority for overlapping entities."""
        entity_map: dict[str, ExtractedEntity] = {}

        # Add secondary first
        for e in secondary.entities:
            entity_map[e.name] = e

        # Override with primary (higher confidence)
        for e in primary.entities:
            entity_map[e.name] = e

        # Merge relations
        relation_map: dict[str, ExtractedRelation] = {}
        for r in secondary.relations:
            key = f"{r.from_entity}|{r.to_entity}|{r.relation_type}"
            relation_map[key] = r
        for r in primary.relations:
            key = f"{r.from_entity}|{r.to_entity}|{r.relation_type}"
            relation_map[key] = r

        return ExtractionResult(
            entities=list(entity_map.values()),
            relations=list(relation_map.values()),
        )
