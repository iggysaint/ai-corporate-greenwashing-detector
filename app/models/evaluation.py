"""Evaluation domain models and API response schemas for Phase 6 LLM & Consistency Engine."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.company import Company


class AssessmentCategory(str, Enum):
    """Controlled vocabulary for evidence-based claim evaluation.

    IMPORTANT: These are objective analytical research assessments based strictly
    on retrieved filing evidence. They do NOT make legal fraud allegations or
    greenwashing accusations.
    """

    SUPPORTED = "supported"
    """Claim commitments or achievements are directly corroborated by affirmative disclosure evidence."""

    PARTIALLY_SUPPORTED = "partially_supported"
    """Disclosures corroborate parts of the claim, but highlight material caveats, limitations, or partial scope."""

    INCONSISTENT = "inconsistent"
    """Disclosed metrics, dates, or factual statements contradict the claim's commitments or assertions."""

    UNSUBSTANTIATED = "unsubstantiated"
    """Claim makes specific assertions, but the filing provides only generic context or no substantive corroboration despite relevant disclosures."""

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    """No relevant evidence passages exist in the filing for the claim."""


class EvaluationConfidence(str, Enum):
    """Confidence level in the evidence evaluation."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvaluationMode(str, Enum):
    """Specifies whether evaluation was produced by an LLM or deterministic rule-based fallback."""

    LLM = "llm"
    RULE_BASED = "rule_based"


class EvidenceReference(BaseModel):
    """Citation of an evidence passage used in a claim evaluation."""

    evidence_id: str = Field(..., description="ID of the referenced Evidence record")
    section_id: str = Field(..., description="10-K section where evidence was found (e.g. item_1, item_7)")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance score from evidence retrieval")
    relationship: str = Field(..., description="Retrieval relationship (supporting, qualifying, contextual, etc.)")
    quote: str = Field(..., description="Verbatim quote or excerpt from the evidence passage")

    model_config = ConfigDict(str_strip_whitespace=True)


class LLMRawAssessment(BaseModel):
    """Internal model for structured LLM response parsing and validation."""

    assessment: AssessmentCategory = Field(..., description="Evaluated assessment category")
    confidence: EvaluationConfidence = Field(..., description="Confidence level in the assessment")
    reasoning: str = Field(..., description="Objective, analytical reasoning grounded strictly in the supplied evidence")
    caveats: List[str] = Field(default_factory=list, description="Key qualifications, limitations, or scope restrictions")
    referenced_evidence_ids: List[str] = Field(
        default_factory=list,
        description="List of evidence_ids directly supporting this assessment",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class ClaimEvaluation(BaseModel):
    """Structured evaluation of a sustainability claim against its retrieved evidence."""

    evaluation_id: str = Field(..., description="Deterministic or unique evaluation identifier")
    claim_id: str = Field(..., description="ID of the claim evaluated")
    company_ticker: str = Field(..., description="Normalized company ticker symbol")
    company_name: str = Field(..., description="Registered company name")
    claim_text: str = Field(..., description="Original claim text")
    claim_type: str = Field(..., description="Claim type: target, achievement, current_state, policy, general")
    category: str = Field(..., description="Thematic ESG category")
    category_group: str = Field(..., description="Pillar: environmental, social, governance")

    # Assessment details
    assessment: AssessmentCategory = Field(
        ...,
        description="Objective analytical assessment: supported, partially_supported, inconsistent, unsubstantiated, or insufficient_evidence",
    )
    confidence: EvaluationConfidence = Field(..., description="Confidence in this assessment")
    reasoning: str = Field(
        ...,
        description="Analytical explanation of why this assessment was reached based on the evidence",
    )
    caveats: List[str] = Field(
        default_factory=list,
        description="Specific caveats, exceptions, or scope limitations identified",
    )
    referenced_evidence: List[EvidenceReference] = Field(
        default_factory=list,
        description="Validated evidence passages cited in the evaluation",
    )

    # Provenance and metadata
    evaluation_mode: EvaluationMode = Field(
        ...,
        description="Evaluation source: 'llm' for AI-generated assessment, 'rule_based' for deterministic fallback",
    )
    model_name: Optional[str] = Field(None, description="Name of LLM model used (or None if rule_based)")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC ISO 8601 timestamp when evaluation was created",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class EvaluationSummary(BaseModel):
    """Distribution of claim assessments across a company filing."""

    total_claims_evaluated: int = Field(..., description="Total claims evaluated")
    total_claims_extracted: int = Field(0, description="Total claims extracted from filing")
    excluded_claims_count: int = Field(0, description="Claims excluded as non-sustainability or legal/financial boilerplate")
    supported_count: int = Field(0, description="Claims assessed as supported")
    partially_supported_count: int = Field(0, description="Claims assessed as partially supported")
    inconsistent_count: int = Field(0, description="Claims assessed as inconsistent")
    unsubstantiated_count: int = Field(0, description="Claims assessed as unsubstantiated")
    insufficient_evidence_count: int = Field(0, description="Claims assessed as insufficient evidence")
    rule_based_evaluations_count: int = Field(0, description="Number of rule-based evaluations")
    llm_evaluations_count: int = Field(0, description="Number of LLM evaluations")

    model_config = ConfigDict(str_strip_whitespace=True)


class CompanyEvaluationResponse(BaseModel):
    """Aggregate response containing all claim evaluations for a company filing."""

    company: Company = Field(..., description="Company identification metadata")
    filing_accession_number: str = Field(..., description="SEC EDGAR filing accession number")
    form_type: str = Field(..., description="Filing type (e.g. 10-K)")
    filing_date: str = Field(..., description="Filing date (YYYY-MM-DD)")
    report_date: Optional[str] = Field(None, description="Fiscal period end date (YYYY-MM-DD) if known")
    fiscal_year: Optional[int] = Field(None, description="Fiscal year of the filing if known")
    summary: EvaluationSummary = Field(..., description="Assessment breakdown counts")
    evaluations: List[ClaimEvaluation] = Field(..., description="Detailed evaluations for each claim")
    provider_mode: str = Field(..., description="Active execution mode: 'llm' or 'rule_based'")
    model_name: Optional[str] = Field(None, description="Active model name")

    model_config = ConfigDict(str_strip_whitespace=True)


class SingleClaimEvaluationResponse(BaseModel):
    """Response containing an evaluation for an individual claim."""

    evaluation: ClaimEvaluation = Field(..., description="The evaluated claim result")
    provider_mode: str = Field(..., description="Active execution mode: 'llm' or 'rule_based'")

    model_config = ConfigDict(str_strip_whitespace=True)
