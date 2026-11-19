"""Evidence domain models and API response schemas for the Evidence & Cross-Reference Engine."""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.claim import Claim
from app.models.company import Company


class EvidenceRelationship(str, Enum):
    """Controlled vocabulary for the relationship between a claim and an evidence passage.

    IMPORTANT: These classifications represent retrieval/relevance results only.
    They do NOT constitute a determination of greenwashing, fraud, or legal violation.
    """

    SUPPORTING = "supporting"
    """Evidence appears to substantiate or reinforce the claim."""

    CONTRADICTORY = "contradictory"
    """Evidence appears inconsistent with the claim's assertions."""

    QUALIFYING = "qualifying"
    """Evidence limits, narrows, conditions, or adds important context to the claim."""

    CONTEXTUAL = "contextual"
    """Evidence is relevant to the subject matter but does not directly prove or disprove the claim."""

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    """The available filing does not contain enough relevant evidence to establish a meaningful relationship."""


class EvidenceType(str, Enum):
    """Controlled vocabulary for the nature of an evidence passage."""

    QUANTITATIVE = "quantitative"
    """Evidence contains numerical disclosures, metrics, or measurable data."""

    QUALITATIVE = "qualitative"
    """Evidence contains descriptive narrative about practices or performance."""

    TARGET = "target"
    """Evidence describes a forward-looking goal or commitment."""

    ACHIEVEMENT = "achievement"
    """Evidence describes a past result or completed milestone."""

    BASELINE = "baseline"
    """Evidence establishes a reference point or prior-period measurement."""

    POLICY = "policy"
    """Evidence describes a policy, standard, code of conduct, or governance framework."""

    RISK = "risk"
    """Evidence describes a risk factor, uncertainty, or potential adverse condition."""

    OPERATIONAL = "operational"
    """Evidence describes operational practices, processes, or activities."""

    DISCLOSURE = "disclosure"
    """Evidence is a general informational disclosure without a specific metric."""

    FINANCIAL = "financial"
    """Evidence contains financial figures, costs, or economic data."""

    OTHER = "other"
    """Evidence type could not be determined from available information."""


class EvidenceStrength(str, Enum):
    """Deterministic evidence strength classification.

    This is NOT a truth judgment. It reflects retrieval quality and conceptual overlap.
    """

    STRONG = "strong"
    """Direct quantitative disclosure matching the claim's metric and relevant period."""

    MODERATE = "moderate"
    """Relevant disclosure that supports the subject matter but lacks one important component."""

    WEAK = "weak"
    """General contextual information related to the claim, lacking specificity."""


class Evidence(BaseModel):
    """Structured representation of an evidence passage found in an SEC filing.

    Each record preserves full source traceability back to the original regulatory filing.

    IMPORTANT: Evidence records represent retrieved filing content that may be relevant
    to a sustainability claim. They do NOT constitute a greenwashing determination,
    legal assessment, or judgment of corporate conduct.
    """

    evidence_id: str = Field(..., description="Stable deterministic identifier derived from claim ID and evidence content")
    claim_id: str = Field(..., description="Claim ID this evidence was retrieved for")
    company_ticker: str = Field(..., description="Normalized company stock ticker symbol")
    company_name: str = Field(..., description="Official registered company name")

    # Evidence content
    evidence_text: str = Field(..., description="Verbatim passage text from the SEC filing")
    evidence_type: str = Field(..., description="Nature of the evidence (quantitative, qualitative, policy, risk, etc.)")
    relationship: str = Field(
        ...,
        description=(
            "Retrieval relationship to the claim: supporting, contradictory, qualifying, "
            "contextual, or insufficient_evidence. "
            "This is a retrieval classification only and does not constitute a legal or ethical judgment."
        ),
    )

    # Source traceability (required)
    source_type: str = Field("sec_10k", description="Source document type")
    source_title: str = Field(..., description="Document title or filing designation")
    source_url: str = Field(..., description="Direct HTTPS URL to source filing on SEC EDGAR")
    filing_accession_number: str = Field(..., description="SEC EDGAR accession number")
    filing_date: str = Field(..., description="Filing submission date (YYYY-MM-DD)")
    report_date: Optional[str] = Field(None, description="Fiscal period end date (YYYY-MM-DD)")
    section_id: str = Field(..., description="10-K section identifier (e.g. 'item_7', 'item_1a')")
    section_title: str = Field(..., description="10-K section title")
    source_location: str = Field(..., description="Human-readable section location string")
    approximate_position: int = Field(..., description="Approximate character offset within the document section")

    # Matching metadata
    matched_concepts: List[str] = Field(
        default_factory=list,
        description="High-level concepts from the claim found in this evidence passage",
    )
    matched_terms: List[str] = Field(
        default_factory=list,
        description="Specific keyword terms from the claim found in this evidence passage",
    )

    # Scoring (retrieval quality only)
    relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Deterministic retrieval relevance score (0.0–1.0). "
            "Reflects conceptual overlap between claim and evidence. "
            "NOT a truth score, greenwashing score, or ESG score."
        ),
    )
    evidence_strength: str = Field(
        ...,
        description="Deterministic evidence strength: strong, moderate, or weak. "
                    "Reflects retrieval quality, not a judgment of claim accuracy.",
    )
    extraction_method: str = Field("deterministic", description="Always 'deterministic' in Phase 5")
    confidence: str = Field("medium", description="Internal confidence: high, medium, low")

    model_config = ConfigDict(str_strip_whitespace=True)


class ClaimEvidenceResult(BaseModel):
    """Structured result pairing a single sustainability claim with its retrieved evidence.

    IMPORTANT: The relationships presented here are retrieval results only.
    They do NOT constitute a determination of greenwashing or legal violation.
    Phase 6 will apply LLM-based reasoning over these results.
    """

    claim: Claim = Field(..., description="The source sustainability claim")
    evidence: List[Evidence] = Field(default_factory=list, description="All retrieved evidence records")
    best_evidence: List[Evidence] = Field(
        default_factory=list,
        description="Top evidence records by relevance score (up to 3)",
    )
    evidence_count: int = Field(..., description="Total number of evidence records retrieved")
    strongest_relationship: str = Field(
        ...,
        description=(
            "Predominant retrieval relationship among evidence records: "
            "supporting, contradictory, qualifying, contextual, or insufficient_evidence. "
            "This is a retrieval summary only. It does NOT constitute a greenwashing determination."
        ),
    )
    overall_retrieval_confidence: str = Field(
        ...,
        description="Overall retrieval confidence for this claim: high, medium, low, or insufficient",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class EvidenceSummaryResponse(BaseModel):
    """High-level summary of evidence retrieval across all claims for a company.

    IMPORTANT: Counts presented here reflect evidence retrieval results only.
    They do NOT constitute ESG scoring, greenwashing assessment, or legal conclusions.
    """

    company: Company = Field(..., description="Company identification metadata")
    filing_accession_number: str = Field(..., description="Source SEC filing accession number")
    total_claims_analyzed: int = Field(..., description="Total claims submitted for evidence retrieval")
    claims_with_evidence: int = Field(..., description="Claims for which at least one evidence passage was found")
    claims_insufficient_evidence: int = Field(..., description="Claims for which no meaningful evidence was found")

    # Relationship counts (retrieval classifications)
    supporting_evidence_count: int = Field(..., description="Total supporting evidence records")
    contradictory_evidence_count: int = Field(..., description="Total contradictory evidence records")
    qualifying_evidence_count: int = Field(..., description="Total qualifying evidence records")
    contextual_evidence_count: int = Field(..., description="Total contextual evidence records")

    # Strength counts
    strong_evidence_count: int = Field(..., description="Total strong-strength evidence records")
    moderate_evidence_count: int = Field(..., description="Total moderate-strength evidence records")
    weak_evidence_count: int = Field(..., description="Total weak-strength evidence records")

    extraction_method: str = Field("deterministic", description="Evidence extraction method used")


class CompanyEvidenceResponse(BaseModel):
    """Full evidence retrieval response for all company claims.

    IMPORTANT: This response contains retrieval-based evidence classifications only.
    No greenwashing determination, ESG score, or legal conclusion is produced.
    Phase 6 will apply LLM-based reasoning over these evidence records.
    """

    company: Company = Field(..., description="Company identification metadata")
    filing_accession_number: str = Field(..., description="Source SEC filing accession number")
    filing_date: str = Field(..., description="Filing submission date")
    report_date: Optional[str] = Field(None, description="Fiscal period end date")
    source_url: str = Field(..., description="SEC EDGAR filing URL")
    total_claims: int = Field(..., description="Total claims analyzed")
    total_evidence_records: int = Field(..., description="Total evidence records retrieved across all claims")
    extraction_method: str = Field("deterministic", description="Evidence extraction method")
    results: List[ClaimEvidenceResult] = Field(
        default_factory=list,
        description="Per-claim evidence retrieval results",
    )
