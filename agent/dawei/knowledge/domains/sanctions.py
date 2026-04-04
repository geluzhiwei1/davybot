# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Sanctions & financial crime domain profile for knowledge graph extraction.

Designed to process:
- Sanctions designation documents (OFAC SDN, UN SC lists, EU, UK OFSI, OFAC non-SDN, etc.)
- PEP (Politically Exposed Person) reports
- Debarment and regulatory watchlist records
- AML/CTF investigation reports and court rulings
- ICIJ / OCCRP leak documents (Panama Papers, Pandora Papers, etc.)
- Beneficial ownership and corporate transparency filings

Entity model is aligned with OpenSanctions FollowTheMoney (FtM) schema:
https://www.opensanctions.org/reference/
"""

from .base import DomainProfile


class SanctionsProfile(DomainProfile):
    """制裁及金融犯罪领域画像

    覆盖制裁指定文件、PEP 数据、合规监管名单、反洗钱/反恐融资报告、
    受益所有权文件及国际调查性新闻（ICIJ/OCCRP）等场景。
    """

    name = "sanctions"
    display_name = "制裁 & 合规"
    description = (
        "制裁、PEP 及金融犯罪知识图谱，适用于 OFAC/UN/EU/UK 制裁名单、"
        "反洗钱报告、受益所有权穿透分析及国际调查性新闻等场景"
    )

    # ------------------------------------------------------------------ #
    # Entity types — aligned with FtM schema node types                   #
    # ------------------------------------------------------------------ #
    entity_types = {
        # Sanctioned / listed subjects
        "PERSON": "自然人/当事人 (FtM: Person)",
        "COMPANY": "公司/企业/信托/基金 (FtM: Company)",
        "ORGANIZATION": "非营利/国家机构/组织 (FtM: Organization / PublicBody)",
        "VESSEL": "船舶/船只 (FtM: Vessel)",
        "AIRCRAFT": "飞机/直升机 (FtM: Airplane)",
        "CRYPTO_WALLET": "加密货币钱包/地址 (FtM: CryptoWallet)",
        "SECURITY": "证券/金融工具 (FtM: Security)",
        # Designation & regulatory
        "SANCTION": "制裁指定记录 (FtM: Sanction)",
        "PROGRAM": "制裁项目/名单来源",
        "AUTHORITY": "制裁发起机构/监管机构",
        "POSITION": "政治/公职职务 (FtM: Position / Occupancy)",
        # Identity & document
        "PASSPORT": "护照/证件 (FtM: Passport / Identification)",
        "ADDRESS": "地址/注册地 (FtM: Address)",
        "JURISDICTION": "国家/地区/司法辖区",
        # Asset & financial
        "ASSET": "资产/财产 (FtM: Asset)",
        "PAYMENT": "资金转移/付款记录 (FtM: Payment)",
        # Relationship (interstitial)
        "OWNERSHIP": "股权/受益所有权关系 (FtM: Ownership)",
        "DIRECTORSHIP": "董事/高管任命关系 (FtM: Directorship)",
        "FAMILY": "家庭亲属关系 (FtM: Family)",
        "ASSOCIATE": "关联人关系 (FtM: Associate)",
    }

    # ------------------------------------------------------------------ #
    # Relation types — map to FtM interstitial entity semantics           #
    # ------------------------------------------------------------------ #
    relation_types = {
        # Designation / listing
        "designated_by": "由该机构制裁指定",
        "listed_on": "列入制裁项目/名单",
        "delisted_from": "从制裁名单移除",
        "designated_for": "因该事由/活动被制裁",
        # Corporate structure
        "owns": "持有股权/受益所有 (Ownership)",
        "controlled_by": "受其控制/指示",
        "director_of": "担任董事/高管 (Directorship)",
        "member_of": "成员/附属关系 (Membership)",
        "subsidiary_of": "子公司/下属实体",
        "successor_of": "法律继承自 (Succession)",
        # Political exposure
        "holds_position": "担任政治/公职职务 (Occupancy)",
        "employed_by": "受雇于机构 (Employment)",
        # Personal relations
        "family_of": "家庭亲属关系 (Family)",
        "associate_of": "非家庭关联人 (Associate)",
        "represents": "代理/中间人关系 (Representation)",
        # Asset & financial flows
        "owns_asset": "持有/控制资产",
        "operates_vessel": "运营/控制船舶",
        "registered_in": "注册地/旗籍辖区",
        "identified_by": "由该证件标识 (Passport / Identification)",
        "transacted_with": "资金往来/付款关系 (Payment)",
    }

    # ------------------------------------------------------------------ #
    # Dictionaries — seed terms for rule-based matching                   #
    # ------------------------------------------------------------------ #
    dictionaries = {
        "sanction_programs": [
            # US
            "OFAC SDN", "OFAC Non-SDN", "OFAC Consolidated", "OFAC CAPTA",
            "OFAC NS-MBS List", "US BIS Entity List", "US AECA Debarred",
            # UN
            "UN Security Council", "UNSCR 1267", "UNSCR 1988", "UNSCR 1718",
            "UN Consolidated List",
            # EU
            "EU Consolidated Sanctions", "EU Restrictive Measures",
            # UK
            "UK OFSI", "UK Sanctions List",
            # Other multilateral / national
            "Australian DFAT", "Canadian SEMA", "Swiss SECO",
            "Japan METI", "INTERPOL Red Notice",
        ],
        "listing_authorities": [
            "OFAC", "US Treasury", "US Department of State",
            "European Commission", "Council of the EU",
            "UK OFSI", "HM Treasury",
            "UN Security Council", "UN 1267 Committee",
            "FATF", "Egmont Group",
            "World Bank Integrity Vice Presidency",
            "Asian Development Bank OAI",
            "美国财政部", "欧盟委员会", "联合国安理会", "英国财政部",
            "中国商务部", "中华人民共和国财政部",
        ],
        "risk_topics": [
            # FtM topic tags used in OpenSanctions
            "sanction", "debarment", "role.pep", "role.rca",
            "crime.terror", "crime.proliferation", "crime.cyber",
            "crime.narcotics", "crime.corruption", "crime.money_laundering",
            "crime.traffick", "export.control", "poi",
        ],
        "legal_suffixes": [
            "Corp", "Corporation", "Inc", "Incorporated", "Ltd", "Limited",
            "LLC", "LLP", "PLC", "GmbH", "S.A.", "B.V.", "AG", "N.V.", "S.E.",
            "JSC", "OJSC", "PJSC", "CJSC",            # Russian/CIS forms
            "有限责任公司", "股份有限公司", "集团", "控股", "投资",
        ],
    }

    dictionary_entity_map = {
        "sanction_programs": "PROGRAM",
        "listing_authorities": "AUTHORITY",
        "risk_topics": "SANCTION",
        "legal_suffixes": "COMPANY",
    }

    # ------------------------------------------------------------------ #
    # Patterns — regex for identifiers common in sanctions documents       #
    # ------------------------------------------------------------------ #
    patterns = {
        # US OFAC SDN record ID
        "ofac_id": [
            r"\bOFAC[-\s]?(?:SDN[-\s]?)?\d+\b",
            r"\bSDN[-\s]?\d+\b",
        ],
        # UN Security Council designation number
        "unsc_id": [
            r"\bQDe?\.\d{3,4}(?:\.\d{2})?\b",   # QDe.001 / QDi.123.07
            r"\bTAi?\.\d{3,4}\b",
        ],
        # EU Sanctions identifier
        "eu_id": [
            r"\bEU[-\s]\d{4,10}\b",
        ],
        # ISIN (financial security)
        "isin": [
            r"\b[A-Z]{2}[A-Z0-9]{9}\d\b",
        ],
        # LEI (Legal Entity Identifier — ISO 17442)
        "lei": [
            r"\b[A-Z0-9]{18}\d{2}\b",
        ],
        # IMO vessel number
        "imo_number": [
            r"\bIMO[\s:]*\d{7}\b",
        ],
        # MMSI (Maritime Mobile Service Identity)
        "mmsi": [
            r"\bMMSI[\s:]*\d{9}\b",
        ],
        # Passport / travel document number
        "passport_no": [
            r"\b[A-Z]{1,2}\d{6,9}\b",
        ],
        # Cryptocurrency wallet addresses (BTC, ETH)
        "crypto_address": [
            r"\b1[13-9A-HJ-NP-Za-km-z]{25,34}\b",   # BTC P2PKH
            r"\b3[1-9A-HJ-NP-Za-km-z]{25,34}\b",    # BTC P2SH
            r"\bbc1[ac-hj-np-z02-9]{6,87}\b",        # BTC bech32
            r"\b0x[0-9a-fA-F]{40}\b",                # ETH / ERC-20
        ],
        # General date ranges common in sanction records
        "listing_date": [
            r"\b(?:listed|designated|added)\s+(?:on\s+)?(?:\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}-\d{2}-\d{2})\b",
        ],
        # Beneficial ownership percentage
        "ownership_pct": [
            r"\b\d{1,3}(?:\.\d{1,2})?\s*%\s*(?:ownership|stake|interest|shares?|equity|holding)\b",
            r"\b(?:ownership|stake|interest|shares?|equity|holding)\s+of\s+\d{1,3}(?:\.\d{1,2})?\s*%\b",
        ],
    }

    pattern_entity_map = {
        "ofac_id": "SANCTION",
        "unsc_id": "SANCTION",
        "eu_id": "SANCTION",
        "isin": "SECURITY",
        "lei": "COMPANY",
        "imo_number": "VESSEL",
        "mmsi": "VESSEL",
        "passport_no": "PASSPORT",
        "crypto_address": "CRYPTO_WALLET",
        "listing_date": "SANCTION",
        "ownership_pct": "OWNERSHIP",
    }

    # ------------------------------------------------------------------ #
    # LLM extraction prompt                                                #
    # ------------------------------------------------------------------ #
    extraction_prompt = """你是一名专业的制裁合规与金融犯罪知识图谱构建助手。请从以下文本中提取实体和关系。

文本内容：
{text}

请严格按照以下JSON格式返回，不要添加任何其他内容：

{{
    "entities": [
        {{
            "name": "实体名称（保留原文语言和官方拼写）",
            "type": "类型",
            "properties": {{
                "aliases": ["别名1", "别名2"],
                "jurisdiction": "注册地/国籍/旗籍",
                "sanction_program": "所属制裁项目",
                "listing_date": "制裁生效日期",
                "id_numbers": {{"OFAC": "xxx", "ISIN": "xxx", "IMO": "xxx"}},
                "topics": ["sanction", "role.pep"],
                "status": "Active/Inactive/Expired"
            }}
        }}
    ],
    "relations": [
        {{
            "from_entity": "实体1",
            "to_entity": "实体2",
            "relation_type": "关系类型",
            "properties": {{
                "start_date": "关系开始日期",
                "end_date": "关系结束日期",
                "percentage": "持股比例（如有）",
                "role": "角色/职务（如有）",
                "source": "信息来源"
            }}
        }}
    ]
}}

实体类型：{entity_types}
关系类型：{relation_types}

提取规则：
1. 【实体识别】优先提取被制裁/列名主体（PERSON、COMPANY、VESSEL、AIRCRAFT、CRYPTO_WALLET），以及制裁记录本身（SANCTION）和发起机构（AUTHORITY、PROGRAM）。
2. 【名称处理】保留原文官方名称、所有别名（alias）和曾用名（previousName），包括西里尔字母、阿拉伯字母等非拉丁文字。
3. 【标识符提取】精确提取 OFAC ID、UN SC 编号（QDe/QDi/TAi）、LEI、ISIN、IMO 编号、护照号、加密钱包地址等唯一标识，放入 properties.id_numbers。
4. 【关系穿透】尽量识别受益所有权链（owns → subsidiary_of）、董事/高管关系（director_of）、家庭亲属（family_of）和关联人（associate_of），并标注百分比和日期。
5. 【制裁信息】记录制裁项目（PROGRAM）、主管机构（AUTHORITY）、指定事由、生效日期及到期/撤销日期。
6. 【PEP 信息】对政治公众人物提取职务（POSITION）、任职机构（ORGANIZATION）、任职时间段（holds_position）。
7. 【金融流动】如涉及资金转移，提取付款人/受益人（transacted_with）及金额、货币、日期。
8. 【不确定信息】置信度低的实体或关系应在 properties 中注明 "confidence": "low" 或 "source": "inferred"。
9. 仅提取文本中明确出现或可直接推断的信息，不要凭借背景知识补全未提及的事实。
"""
