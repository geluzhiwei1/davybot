# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""IP SDK data models — typed response objects mirroring the backend API schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ─── Task ───


@dataclass
class TaskResponse:
    task_id: str


# ─── Common ───


@dataclass
class ExportInfo:
    download_url: str = ""
    filename: str = ""
    format: str = ""


@dataclass
class FileUploadResult:
    file_id: str = ""
    filename: str = ""
    size: int = 0
    content_type: str = ""


@dataclass
class WrappedResponse:
    """Generic API response wrapper."""
    success: bool = False
    data: Any | None = None


# ─── M1 创意保护舱 ───


@dataclass
class PriorArt:
    title: str = ""
    relevance: str = ""
    key_differences: str = ""


@dataclass
class NoveltyAnalysis:
    score: int = 0
    closest_prior_arts: list[PriorArt] = field(default_factory=list)
    summary: str = ""


@dataclass
class Inventiveness:
    score: int = 0
    technical_problem: str = ""
    non_obviousness: str = ""
    summary: str = ""


@dataclass
class IndustrialApplicability:
    score: int = 0
    applicable_industries: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class ProtectionSuggestion:
    type: str = ""
    priority: str = ""
    rationale: str = ""


@dataclass
class IdeaItem:
    id: str = ""
    title: str = ""
    description: str = ""
    patentability_score: int = 0
    novelty_analysis: NoveltyAnalysis | None = None
    inventiveness: Inventiveness | None = None
    industrial_applicability: IndustrialApplicability | None = None
    protection_suggestions: list[ProtectionSuggestion] = field(default_factory=list)
    recommended_strategy: str = ""
    status: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IdeaItem:
        return cls(
            id=d.get("id", ""),
            title=d.get("title", ""),
            description=d.get("description", ""),
            patentability_score=d.get("patentabilityScore", 0),
            novelty_analysis=NoveltyAnalysis(
                score=d.get("noveltyAnalysis", {}).get("score", 0), closest_prior_arts=[
                        PriorArt(**pa) for pa in d.get("noveltyAnalysis", {}).get("closestPriorArts", [])
                    ], summary=d.get("noveltyAnalysis", {}).get("summary", "")
            ) if d.get("noveltyAnalysis") else None,
            inventiveness=Inventiveness(
                score=d.get("inventiveness", {}).get("score", 0), technical_problem=d.get("inventiveness", {}).get("technicalProblem", ""), non_obviousness=d.get("inventiveness", {}).get("nonObviousness", ""), summary=d.get("inventiveness", {}).get("summary", "")
            ) if d.get("inventiveness") else None,
            industrial_applicability=IndustrialApplicability(
                score=d.get("industrialApplicability", {}).get("score", 0), applicable_industries=d.get("industrialApplicability", {}).get("applicableIndustries", []), summary=d.get("industrialApplicability", {}).get("summary", "")
            ) if d.get("industrialApplicability") else None,
            protection_suggestions=[
                ProtectionSuggestion(**ps) for ps in d.get("protectionSuggestions", [])
            ],
            recommended_strategy=d.get("recommendedStrategy", ""),
            status=d.get("status", ""),
        )


@dataclass
class IdeaResultResponse:
    success: bool = False
    data: IdeaItem | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IdeaResultResponse:
        return cls(
            success=d.get("success", False),
            data=IdeaItem.from_dict(d["data"]) if d.get("data") else None,
        )


# ─── M2 交底书 ───


@dataclass
class DisclosureSection:
    title: str = ""
    content: str = ""


@dataclass
class IpDisclosure:
    id: str = ""
    title: str = ""
    status: str = ""
    sections: dict[str, DisclosureSection] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IpDisclosure:
        raw_sections = d.get("sections", {})
        sections = {
            key: DisclosureSection(
                title=val.get("title", key),
                content=val.get("content", ""),
            )
            for key, val in raw_sections.items()
        }
        return cls(
            id=d.get("id", ""),
            title=d.get("title", ""),
            status=d.get("status", ""),
            sections=sections,
        )


@dataclass
class DisclosureResultResponse:
    success: bool = False
    data: IpDisclosure | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DisclosureResultResponse:
        return cls(
            success=d.get("success", False),
            data=IpDisclosure.from_dict(d["data"]) if d.get("data") else None,
        )


# ─── M3 智能撰写 ───


@dataclass
class Claim:
    id: str = ""
    number: int = 0
    type: str = ""
    content: str = ""


@dataclass
class Specification:
    technical_field: str = ""
    background_art: str = ""
    summary: str = ""
    detailed_description: str = ""
    examples: str = ""


@dataclass
class ComplianceIssue:
    type: str = ""
    message: str = ""
    severity: str = ""


@dataclass
class ComplianceCheck:
    overall_status: str = ""
    issues: list[ComplianceIssue] = field(default_factory=list)


@dataclass
class IpDraft:
    id: str = ""
    title: str = ""
    target_country: str = ""
    status: str = ""
    strategy: str = ""
    claims: list[Claim] = field(default_factory=list)
    specification: Specification | None = None
    compliance_check: ComplianceCheck | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IpDraft:
        return cls(
            id=d.get("id", ""),
            title=d.get("title", ""),
            target_country=d.get("targetCountry", ""),
            status=d.get("status", ""),
            strategy=d.get("strategy", ""),
            claims=[Claim(**c) for c in d.get("claims", [])],
            specification=Specification(technical_field=d.get("specification", {}).get("technicalField", ""), background_art=d.get("specification", {}).get("backgroundArt", ""), summary=d.get("specification", {}).get("summary", ""), detailed_description=d.get("specification", {}).get("detailedDescription", ""), examples=d.get("specification", {}).get("examples", "")) if d.get("specification") else None,
            compliance_check=ComplianceCheck(
                overall_status=d.get("complianceCheck", {}).get("overallStatus", ""),
                issues=[
                    ComplianceIssue(**iss) for iss in d.get("complianceCheck", {}).get("issues", [])
                ],
            ) if d.get("complianceCheck") else None,
        )


@dataclass
class DraftResultResponse:
    success: bool = False
    data: IpDraft | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DraftResultResponse:
        return cls(
            success=d.get("success", False),
            data=IpDraft.from_dict(d["data"]) if d.get("data") else None,
        )


# ─── M4 申请管家 ───


@dataclass
class PathComparison:
    paris_path: dict[str, Any] = field(default_factory=dict)
    pct_path: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""


@dataclass
class PriorityItem:
    id: str = ""
    country: str = ""
    filing_date: str = ""
    application_number: str = ""
    deadline: str = ""


@dataclass
class FeeItem:
    country: str = ""
    official_fee: float = 0
    agent_fee: float = 0
    total: float = 0
    note: str = ""


@dataclass
class PctStage:
    stage: str = ""
    name: str = ""
    deadline: str = ""
    status: str = ""
    description: str = ""


@dataclass
class FilingTranslation:
    source_lang: str = ""
    target_lang: str = ""
    target_country: str = ""
    status: str = ""
    filename: str = ""


@dataclass
class IpFiling:
    id: str = ""
    draft_id: str = ""
    status: str = ""
    target_markets: list[str] = field(default_factory=list)
    recommended_path: str = ""
    path_comparison: PathComparison | None = None
    priorities: list[PriorityItem] = field(default_factory=list)
    fees: list[FeeItem] = field(default_factory=list)
    pct_timeline: list[PctStage] = field(default_factory=list)
    translations: list[FilingTranslation] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IpFiling:
        return cls(
            id=d.get("id", ""),
            draft_id=d.get("draftId", ""),
            status=d.get("status", ""),
            target_markets=d.get("targetMarkets", []),
            recommended_path=d.get("recommendedPath", ""),
            path_comparison=PathComparison(paris_path=d.get("pathComparison", {}).get("parisPath", {}), pct_path=d.get("pathComparison", {}).get("pctPath", {}), recommendation=d.get("pathComparison", {}).get("recommendation", "")) if d.get("pathComparison") else None,
            priorities=[PriorityItem(**p) for p in d.get("priorities", [])],
            fees=[FeeItem(
                country=f.get("country", ""),
                official_fee=f.get("officialFee", 0),
                agent_fee=f.get("agentFee", 0),
                total=f.get("total", 0),
                note=f.get("note", ""),
            ) for f in d.get("fees", [])],
            pct_timeline=[PctStage(**s) for s in d.get("pctTimeline", [])],
            translations=[FilingTranslation(
                source_lang=t.get("sourceLang", ""),
                target_lang=t.get("targetLang", ""),
                target_country=t.get("targetCountry", ""),
                status=t.get("status", ""),
                filename=t.get("filename", ""),
            ) for t in d.get("translations", [])],
        )


@dataclass
class FilingResultResponse:
    success: bool = False
    data: IpFiling | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FilingResultResponse:
        return cls(
            success=d.get("success", False),
            data=IpFiling.from_dict(d["data"]) if d.get("data") else None,
        )


# ─── M5 OA 答复 ───


@dataclass
class Rejection:
    type: str = ""
    legal_basis: str = ""
    description: str = ""
    strength: str = ""


@dataclass
class ComparedDocument:
    id: str = ""
    title: str = ""
    relevance: str = ""
    comparison: str = ""


@dataclass
class StrategyAnalysis:
    arguable: list[str] = field(default_factory=list)
    claim_amendments: list[str] = field(default_factory=list)


@dataclass
class ReplyItem:
    type: str = ""
    legal_basis: str = ""
    content: str = ""
    strength: str = ""


@dataclass
class AmendedClaim:
    number: int = 0
    type: str = ""
    content: str = ""
    changes: str = ""


@dataclass
class IpOaRecord:
    id: str = ""
    draft_id: str = ""
    status: str = ""
    country: str = ""
    oa_number: str = ""
    oa_date: str = ""
    deadline: str = ""
    rejections: list[Rejection] = field(default_factory=list)
    compared_documents: list[ComparedDocument] = field(default_factory=list)
    recommended_strategy: str = ""
    strategy_analysis: StrategyAnalysis | None = None
    replies: list[ReplyItem] = field(default_factory=list)
    amended_claims: list[AmendedClaim] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IpOaRecord:
        return cls(
            id=d.get("id", ""),
            draft_id=d.get("draftId", ""),
            status=d.get("status", ""),
            country=d.get("country", ""),
            oa_number=d.get("oaNumber", ""),
            oa_date=d.get("oaDate", ""),
            deadline=d.get("deadline", ""),
            rejections=[Rejection(**r) for r in d.get("rejections", [])],
            compared_documents=[ComparedDocument(**cd) for cd in d.get("comparedDocuments", [])],
            recommended_strategy=d.get("recommendedStrategy", ""),
            strategy_analysis=StrategyAnalysis(
                arguable=d.get("strategyAnalysis", {}).get("arguable", []),
                claim_amendments=d.get("strategyAnalysis", {}).get("claimAmendments", []),
            ) if d.get("strategyAnalysis") else None,
            replies=[ReplyItem(**r) for r in d.get("replies", [])],
            amended_claims=[AmendedClaim(**ac) for ac in d.get("amendedClaims", [])],
        )


@dataclass
class OaReplyResultResponse:
    success: bool = False
    data: IpOaRecord | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OaReplyResultResponse:
        return cls(
            success=d.get("success", False),
            data=IpOaRecord.from_dict(d["data"]) if d.get("data") else None,
        )


# ─── M6 侵权雷达 ───


@dataclass
class FeatureMapping:
    claim_element: str = ""
    product_feature: str = ""
    match_level: str = ""


@dataclass
class FtoResult:
    patent_number: str = ""
    title: str = ""
    risk_level: str = ""
    risk_score: int = 0
    feature_mapping: list[FeatureMapping] = field(default_factory=list)
    analysis: str = ""


@dataclass
class PatentWatchItem:
    id: str = ""
    title: str = ""
    relevance: int = 0
    filing_date: str = ""
    status: str = ""
    alert_level: str = ""


@dataclass
class TrademarkSimItem:
    id: str = ""
    your_mark: str = ""
    similar_mark: str = ""
    text_similarity: int = 0
    graphic_similarity: int = 0
    class_overlap: list[int] = field(default_factory=list)
    confusion_likelihood: int = 0
    overall_risk: str = ""


@dataclass
class Alert:
    id: str = ""
    level: str = ""
    title: str = ""
    description: str = ""
    created_at: str = ""
    read: bool = False


@dataclass
class IpInfringement:
    id: str = ""
    status: str = ""
    type: str = ""
    product_description: str = ""
    target_patents: list[str] = field(default_factory=list)
    fto_results: list[FtoResult] = field(default_factory=list)
    patent_watchlist: list[PatentWatchItem] = field(default_factory=list)
    trademark_similarity: list[TrademarkSimItem] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IpInfringement:
        return cls(
            id=d.get("id", ""),
            status=d.get("status", ""),
            type=d.get("type", ""),
            product_description=d.get("productDescription", ""),
            target_patents=d.get("targetPatents", []),
            fto_results=[
                FtoResult(
                    patent_number=fr.get("patentNumber", ""),
                    title=fr.get("title", ""),
                    risk_level=fr.get("riskLevel", ""),
                    risk_score=fr.get("riskScore", 0),
                    feature_mapping=[
                        FeatureMapping(**fm) for fm in fr.get("featureMapping", [])
                    ],
                    analysis=fr.get("analysis", ""),
                )
                for fr in d.get("ftoResults", [])
            ],
            patent_watchlist=[
                PatentWatchItem(**pw) for pw in d.get("patentWatchlist", [])
            ],
            trademark_similarity=[
                TrademarkSimItem(
                    id=ts.get("id", ""),
                    your_mark=ts.get("yourMark", ""),
                    similar_mark=ts.get("similarMark", ""),
                    text_similarity=ts.get("textSimilarity", 0),
                    graphic_similarity=ts.get("graphicSimilarity", 0),
                    class_overlap=ts.get("classOverlap", []),
                    confusion_likelihood=ts.get("confusionLikelihood", 0),
                    overall_risk=ts.get("overallRisk", ""),
                )
                for ts in d.get("trademarkSimilarity", [])
            ],
            alerts=[Alert(**a) for a in d.get("alerts", [])],
        )


@dataclass
class InfringementResultResponse:
    success: bool = False
    data: IpInfringement | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> InfringementResultResponse:
        return cls(
            success=d.get("success", False),
            data=IpInfringement.from_dict(d["data"]) if d.get("data") else None,
        )


# ─── M7 资产仪表盘 ───


@dataclass
class PatentItem:
    id: str = ""
    title: str = ""
    patent_number: str = ""
    status: str = ""
    priority_date: str = ""
    filing_date: str = ""
    grant_date: str = ""
    expiry_date: str = ""
    inventors: list[str] = field(default_factory=list)
    patent_type: str = ""
    value_score: int = 0
    technical_value: int = 0
    legal_value: int = 0
    economic_value: int = 0
    family_size: int = 0
    product_relation: str = ""
    citation_count: int = 0


@dataclass
class TrademarkItem:
    id: str = ""
    name: str = ""
    registration_number: str = ""
    status: str = ""
    classes: list[int] = field(default_factory=list)
    filing_date: str = ""
    registration_date: str = ""
    expiry_date: str = ""


@dataclass
class PatentKpis:
    total: int = 0
    granted: int = 0
    pending: int = 0
    abandoned: int = 0
    expired: int = 0
    this_year: int = 0
    grant_rate: float = 0.0
    avg_claims: float = 0.0
    avg_citations_per_patent: float = 0.0


@dataclass
class TrademarkKpis:
    total: int = 0
    registered: int = 0
    pending: int = 0
    opposed: int = 0
    this_year: int = 0


@dataclass
class Kpis:
    patent: PatentKpis | None = None
    trademark: TrademarkKpis | None = None
    weighted_avg_value_score: float = 0.0


@dataclass
class HealthSubScores:
    quality: int = 0
    coverage: int = 0
    lifespan: int = 0
    business: int = 0


@dataclass
class StatusDistribution:
    status: str = ""
    count: int = 0
    percentage: float = 0.0


@dataclass
class CompetitorItem:
    id: str = ""
    name: str = ""
    patent_count: int = 0
    trademark_count: int = 0
    patent_quality: int = 0
    top_tech_fields: list[str] = field(default_factory=list)
    gap_analysis: dict[str, Any] = field(default_factory=dict)


@dataclass
class RenewalItem:
    title: str = ""
    due_date: str = ""
    fee: float = 0
    recommended_action: str = ""
    year: int = 0
    patent_id: str = ""


@dataclass
class Renewals:
    next_12_months: list[RenewalItem] = field(default_factory=list)
    total_estimated_fees: float = 0.0


@dataclass
class IpPortfolio:
    id: str = ""
    status: str = ""
    patents: list[PatentItem] = field(default_factory=list)
    trademarks: list[TrademarkItem] = field(default_factory=list)
    kpis: Kpis | None = None
    health_score: int = 0
    health_sub_scores: HealthSubScores | None = None
    patent_status_distribution: list[StatusDistribution] = field(default_factory=list)
    competitors: list[CompetitorItem] = field(default_factory=list)
    renewals: Renewals | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IpPortfolio:
        return cls(
            id=d.get("id", ""),
            status=d.get("status", ""),
            patents=[PatentItem(**p) for p in d.get("patents", [])],
            trademarks=[TrademarkItem(**tm) for tm in d.get("trademarks", [])],
            kpis=Kpis(
                patent=PatentKpis(**d.get("kpis", {}).get("patent", {})),
                trademark=TrademarkKpis(**d.get("kpis", {}).get("trademark", {})),
                weighted_avg_value_score=d.get("kpis", {}).get("weightedAvgValueScore", 0.0),
            ) if d.get("kpis") else None,
            health_score=d.get("healthScore", 0),
            health_sub_scores=HealthSubScores(**d.get("healthSubScores", {})) if d.get("healthSubScores") else None,
            patent_status_distribution=[
                StatusDistribution(**sd) for sd in d.get("patentStatusDistribution", [])
            ],
            competitors=[CompetitorItem(**c) for c in d.get("competitors", [])],
            renewals=Renewals(
                next_12_months=[
                    RenewalItem(**r) for r in d.get("renewals", {}).get("next12Months", [])
                ],
                total_estimated_fees=d.get("renewals", {}).get("totalEstimatedFees", 0.0),
            ) if d.get("renewals") else None,
        )


@dataclass
class PortfolioResultResponse:
    success: bool = False
    data: IpPortfolio | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PortfolioResultResponse:
        return cls(
            success=d.get("success", False),
            data=IpPortfolio.from_dict(d["data"]) if d.get("data") else None,
        )


# ─── M8 商标注册 ───


@dataclass
class NiceClass:
    class_number: int = 0
    class_name: str = ""
    type: str = ""
    goods: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass
class Registrability:
    overall_score: int = 0
    overall_rating: str = ""
    distinctiveness: dict[str, Any] = field(default_factory=dict)
    absolute_grounds: dict[str, Any] = field(default_factory=dict)
    relative_grounds: dict[str, Any] = field(default_factory=dict)
    similar_trademarks: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""


@dataclass
class IpTrademark:
    id: str = ""
    name: str = ""
    status: str = ""
    recommended_classes: list[NiceClass] = field(default_factory=list)
    registrability: Registrability | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IpTrademark:
        reg = d.get("registrability", {})
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            status=d.get("status", ""),
            recommended_classes=[
                NiceClass(**nc) for nc in d.get("recommendedClasses", [])
            ],
            registrability=Registrability(
                overall_score=reg.get("overallScore", 0),
                overall_rating=reg.get("overallRating", ""),
                distinctiveness=reg.get("distinctiveness", {}),
                absolute_grounds=reg.get("absoluteGrounds", {}),
                relative_grounds=reg.get("relativeGrounds", {}),
                similar_trademarks=reg.get("similarTrademarks", []),
                summary=reg.get("summary", ""),
            ) if reg else None,
        )


@dataclass
class TrademarkResultResponse:
    success: bool = False
    data: IpTrademark | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TrademarkResultResponse:
        return cls(
            success=d.get("success", False),
            data=IpTrademark.from_dict(d["data"]) if d.get("data") else None,
        )
