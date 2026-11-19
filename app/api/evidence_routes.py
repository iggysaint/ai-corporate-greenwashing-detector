"""API routes for the Evidence & Cross-Reference Engine (Phase 5).

IMPORTANT: Evidence endpoints return retrieval-based classifications only.
They do NOT produce ESG scores, greenwashing determinations, or legal conclusions.
Phase 6 will apply LLM-based reasoning over these evidence records.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.models.evidence import (
    ClaimEvidenceResult,
    CompanyEvidenceResponse,
    EvidenceSummaryResponse,
)
from app.services.evidence_service import EvidenceService, get_evidence_service

router = APIRouter(prefix="/companies", tags=["Evidence"])


@router.get(
    "/{ticker}/evidence/summary",
    response_model=EvidenceSummaryResponse,
    summary="Get Evidence Retrieval Summary",
    description=(
        "Retrieve aggregated summary statistics for evidence retrieval across all claims. "
        "These counts reflect evidence retrieval results only. "
        "They do NOT constitute an ESG score, greenwashing assessment, or legal conclusion."
    ),
)
def get_evidence_summary(
    ticker: str,
    evidence_service: EvidenceService = Depends(get_evidence_service),
) -> EvidenceSummaryResponse:
    """Retrieve high-level summary of evidence retrieval statistics."""
    return evidence_service.get_evidence_summary(ticker=ticker)


@router.get(
    "/{ticker}/claims/{claim_id}/evidence",
    response_model=ClaimEvidenceResult,
    summary="Retrieve Evidence for a Specific Claim",
    description=(
        "Retrieve all evidence passages from the SEC filing relevant to a specific sustainability claim ID. "
        "Evidence records are retrieval-based classifications only and do NOT constitute a "
        "greenwashing determination or legal judgment."
    ),
)
def get_claim_evidence(
    ticker: str,
    claim_id: str,
    evidence_service: EvidenceService = Depends(get_evidence_service),
) -> ClaimEvidenceResult:
    """Retrieve evidence for a specific sustainability claim by ID."""
    return evidence_service.get_claim_evidence(ticker=ticker, claim_id=claim_id)


@router.get(
    "/{ticker}/evidence",
    response_model=CompanyEvidenceResponse,
    summary="Retrieve Evidence for All Sustainability Claims",
    description=(
        "Retrieve SEC filing evidence passages relevant to each extracted sustainability claim. "
        "Evidence records are retrieval-based classifications only and do NOT constitute a "
        "greenwashing determination, ESG score, or legal judgment."
    ),
)
def get_company_evidence(
    ticker: str,
    category: Optional[str] = Query(
        None,
        description="Filter by ESG category or pillar (e.g. 'greenhouse_gas', 'renewable_energy', 'environmental')",
    ),
    claim_type: Optional[str] = Query(
        None,
        description="Filter by claim type: 'target', 'achievement', 'current_state', 'policy', 'general'",
    ),
    relationship: Optional[str] = Query(
        None,
        description=(
            "Filter by predominant evidence relationship: "
            "'supporting', 'contradictory', 'qualifying', 'contextual', 'insufficient_evidence'"
        ),
    ),
    minimum_relevance: float = Query(
        0.0,
        ge=0.0,
        le=1.0,
        description="Minimum relevance score threshold (0.0–1.0, default 0.0 = no filter)",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=500,
        description="Maximum number of claim-evidence results to return (1–500, default 50)",
    ),
    evidence_service: EvidenceService = Depends(get_evidence_service),
) -> CompanyEvidenceResponse:
    """Retrieve evidence for all sustainability claims from the latest 10-K filing."""
    return evidence_service.get_company_evidence(
        ticker=ticker,
        category=category,
        claim_type=claim_type,
        relationship=relationship,
        minimum_relevance=minimum_relevance,
        limit=limit,
    )
