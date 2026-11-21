"""Scoring domain models and API response schemas for Phase 8 ESG Integrity Scoring Engine.

IMPORTANT DISCLAIMER:
    The ESG Integrity Score evaluates ONLY the credibility and evidence substantiation
    of a company's disclosed sustainability claims based on retrieved regulatory filings
    and corporate disclosure documents.
    It is NOT:
    - A complete ESG performance rating.
    - A measure of the company's entire environmental or social impact.
    - Proof that a company is or is not greenwashing.
    - A substitute for an independent ESG audit.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.evaluation import AssessmentCategory
from app.models.market import MarketIdentifier


class ScoreStatus(str, Enum):
    """Status indicator for the ESG Integrity Score."""

    SCORED = "scored"
    INSUFFICIENT_DATA = "insufficient_data"


class ConfidenceLevel(str, Enum):
    """Overall analytical confidence rating for the integrity score."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class DimensionalScore(BaseModel):
    """Scoring breakdown for a single ESG pillar (Environmental, Social, or Governance)."""

    dimension: str = Field(..., description="ESG Pillar: environmental, social, or governance")
    score: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Pillar integrity score (0-100) or None if insufficient data exists",
    )
    status: ScoreStatus = Field(..., description="Scoring status for this pillar")
    weight: float = Field(..., ge=0.0, le=1.0, description="Configured base weight for this pillar")
    effective_weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Active normalized weight after adjusting for available dimensions",
    )
    claims_count: int = Field(0, description="Total claims in this pillar")
    assessable_claims_count: int = Field(0, description="Claims with substantive evidence evaluations")
    supported_count: int = Field(0, description="Directly supported claims")
    partially_supported_count: int = Field(0, description="Partially supported claims")
    inconsistent_count: int = Field(0, description="Contradicted or inconsistent claims")
    unsubstantiated_count: int = Field(0, description="Unsubstantiated claims")
    insufficient_evidence_count: int = Field(0, description="Claims lacking sufficient evidence")
    evidence_coverage: float = Field(
        0.0,
        ge=0.0,
        le=100.0,
        description="Evidence coverage percentage for this pillar",
    )
    confidence: ConfidenceLevel = Field(..., description="Confidence level for this pillar")
    key_factors: List[str] = Field(
        default_factory=list,
        description="Primary factors influencing this pillar result",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class ClaimScoreDetail(BaseModel):
    """Detailed score calculation trace for an individual sustainability claim."""

    claim_id: str = Field(..., description="Unique claim identifier")
    evaluation_id: str = Field(..., description="Unique evaluation identifier")
    claim_text: str = Field(..., description="Extracted claim assertion text")
    claim_type: str = Field(..., description="Type of claim (achievement, target, current_state, policy, general)")
    category: str = Field(..., description="Thematic ESG category")
    category_group: str = Field(..., description="ESG pillar (environmental, social, governance)")
    assessment: AssessmentCategory = Field(..., description="Evaluation outcome")
    base_score: float = Field(..., ge=0.0, le=100.0, description="Baseline score for the assessment category")
    evidence_quality_adjustment: float = Field(
        ...,
        ge=-10.0,
        le=10.0,
        description=(
            "Bounded additive adjustment (points) from evaluation confidence, cited-evidence relevance "
            "and caveats. The adjusted score is clamped to the assessment category's band, so evidence "
            "quality can never move a claim into a different assessment category's range."
        ),
    )
    quality_adjustment_reasons: List[str] = Field(
        default_factory=list,
        description="Human-readable reasons for each evidence quality adjustment applied",
    )
    claim_score: float = Field(..., ge=0.0, le=100.0, description="Adjusted claim integrity score")
    materiality_weight: float = Field(..., ge=0.0, description="Composite materiality weight before volume damping")
    effective_weight: float = Field(
        0.0,
        ge=0.0,
        description=(
            "Weight actually applied in pillar aggregation after low-materiality volume damping. "
            "0.0 for insufficient-evidence claims and claims not mapped to an ESG pillar."
        ),
    )
    included_in_score: bool = Field(
        False,
        description="Whether this claim contributed to a pillar score and the overall score",
    )
    is_quantified: bool = Field(False, description="Whether claim includes specific numerical targets or metrics")
    sector_priority_match: bool = Field(False, description="Whether claim aligns with high-materiality sector themes")
    referenced_evidence_ids: List[str] = Field(
        default_factory=list,
        description="Evidence IDs cited in this claim's assessment",
    )
    caveats_count: int = Field(0, description="Number of caveats noted in evaluation")
    reasoning: str = Field(..., description="Analytical evaluation rationale")

    model_config = ConfigDict(str_strip_whitespace=True)


class ESGIntegrityScoreResponse(BaseModel):
    """Primary response schema for company ESG Integrity Score."""

    company_name: str = Field(..., description="Official registered company title")
    ticker: str = Field(..., description="Stock ticker symbol")
    market: MarketIdentifier = Field(..., description="Market identifier (US_SEC or GH_GSE)")
    reporting_period: Optional[str] = Field(None, description="Fiscal period or annual report year")
    esg_integrity_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Overall ESG Integrity Score (0-100), or None if available data is insufficient",
    )
    score_status: ScoreStatus = Field(..., description="Score status: 'scored' or 'insufficient_data'")
    confidence: ConfidenceLevel = Field(..., description="Analytical confidence level: high, medium, low, or insufficient")
    evidence_coverage: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description=(
            "Percentage of assessed claims for which relevant disclosure evidence was retrieved "
            "(i.e. not 'insufficient_evidence'). Coverage measures data availability, NOT corroboration."
        ),
    )
    substantiation_rate: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description=(
            "Percentage of assessable claims rated supported or partially supported. "
            "None when there are no assessable claims."
        ),
    )

    # Pillar scores
    environmental_score: Optional[float] = Field(None, description="Environmental pillar score (0-100) or None")
    social_score: Optional[float] = Field(None, description="Social pillar score (0-100) or None")
    governance_score: Optional[float] = Field(None, description="Governance pillar score (0-100) or None")

    # Claim counts
    total_claims_extracted: int = Field(0, description="Total sustainability claims extracted from disclosure")
    total_claims_assessed: int = Field(0, description="Total claims evaluated against filing evidence")
    supported_claims: int = Field(0, description="Claims directly corroborated by disclosures")
    partially_supported_claims: int = Field(0, description="Claims partially corroborated with qualifications")
    inconsistent_claims: int = Field(0, description="Claims contradicted by disclosed facts or metrics")
    unsubstantiated_claims: int = Field(0, description="Claims with inadequate substantiation in disclosures")
    insufficient_evidence_claims: int = Field(0, description="Claims with no relevant evidence found")
    unmapped_claims: int = Field(
        0,
        description="Assessed claims whose category is not mapped to E, S or G (excluded from scores)",
    )
    duplicate_evaluations_ignored: int = Field(
        0,
        description="Evaluations ignored because their claim_id was already scored (prevents double counting)",
    )
    rule_based_evaluations: int = Field(0, description="Evaluations produced by the deterministic rule-based engine")
    llm_evaluations: int = Field(0, description="Evaluations produced by the LLM evaluator")

    # Analytical factors
    main_positive_factors: List[str] = Field(
        default_factory=list,
        description="Key disclosures and evidence strengthening integrity",
    )
    main_concerns: List[str] = Field(
        default_factory=list,
        description="Key inconsistencies, unverified targets, or caveats weakening integrity",
    )

    # Metadata & Governance
    methodology_version: str = Field("1.0.0", description="Version of the scoring methodology used")
    assessment_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC timestamp of the assessment",
    )
    source_document_references: List[str] = Field(
        default_factory=list,
        description="Accession numbers, filing URLs, or document identifiers evaluated",
    )
    disclaimer: str = Field(
        (
            "This ESG Integrity Score measures only the substantiation and credibility of disclosed "
            "sustainability claims based on retrieved corporate filing evidence. It does not measure total "
            "environmental or social impact, does not constitute a full ESG performance rating or audit, "
            "and does not make legal determinations regarding greenwashing."
        ),
        description="Mandatory methodological scope and limitation disclaimer",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class ESGScoreBreakdownResponse(ESGIntegrityScoreResponse):
    """Detailed analytical breakdown of the ESG Integrity Score with full calculation transparency."""

    dimensions: Dict[str, DimensionalScore] = Field(
        default_factory=dict,
        description="Detailed pillar-by-pillar scores and statistics",
    )
    claim_scores: List[ClaimScoreDetail] = Field(
        default_factory=list,
        description="Full claim-by-claim scoring calculations, materiality weights, and evidence links",
    )
    materiality_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Sector priority and weighting configuration applied",
    )
    methodology_details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Transparent parameters, base scores, and formula definitions used in this run",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class ESGScoreHistoryResponse(BaseModel):
    """Historical record of available ESG Integrity Scores for a company."""

    company_name: str = Field(..., description="Official registered company title")
    ticker: str = Field(..., description="Stock ticker symbol")
    market: MarketIdentifier = Field(..., description="Market identifier")
    total_records: int = Field(0, description="Number of historical evaluation records available")
    history: List[ESGIntegrityScoreResponse] = Field(
        default_factory=list,
        description="Chronological scoring evaluations",
    )
    note: str = Field(
        "Historical scores are derived from active in-memory cached filing/document evaluations. Persistent database storage is not enabled in this phase.",
        description="Operational context note regarding historical persistence",
    )

    model_config = ConfigDict(str_strip_whitespace=True)
