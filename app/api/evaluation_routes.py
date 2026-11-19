"""API routes for Phase 6 LLM-Assisted Evidence Evaluation & Consistency Verification.

IMPORTANT: Evaluations are objective, evidence-based research assessments.
They do NOT make legal fraud allegations or greenwashing accusations.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.models.evaluation import (
    AssessmentCategory,
    CompanyEvaluationResponse,
    EvaluationSummary,
    SingleClaimEvaluationResponse,
)
from app.services.llm_service import LLMService, get_llm_service

router = APIRouter(prefix="/companies", tags=["Evaluations"])


@router.get(
    "/{ticker}/evaluations/summary",
    response_model=EvaluationSummary,
    summary="Get Claim Evaluation Summary",
    description=(
        "Retrieve aggregated summary statistics of claim assessments (supported, partially_supported, "
        "inconsistent, unsubstantiated, insufficient_evidence). "
        "These assessments are analytical research findings based strictly on filing evidence."
    ),
)
def get_evaluation_summary(
    ticker: str,
    llm_service: LLMService = Depends(get_llm_service),
) -> EvaluationSummary:
    """Retrieve summary distribution of claim assessments for a company."""
    comp_resp = llm_service.evaluate_company_filing(company_ticker=ticker)
    return comp_resp.summary


@router.get(
    "/{ticker}/claims/{claim_id}/evaluation",
    response_model=SingleClaimEvaluationResponse,
    summary="Retrieve Evaluation for a Specific Claim",
    description=(
        "Retrieve the objective, evidence-grounded evaluation for a single sustainability claim ID."
    ),
)
def get_single_claim_evaluation(
    ticker: str,
    claim_id: str,
    llm_service: LLMService = Depends(get_llm_service),
) -> SingleClaimEvaluationResponse:
    """Retrieve the evaluation of a specific sustainability claim by ID."""
    return llm_service.get_single_claim_evaluation(company_ticker=ticker, claim_id=claim_id)


@router.get(
    "/{ticker}/evaluations",
    response_model=CompanyEvaluationResponse,
    summary="Retrieve Claim Evaluations for a Company",
    description=(
        "Evaluate all sustainability claims from the latest 10-K filing against retrieved disclosures. "
        "Each evaluation produces an objective assessment (supported, partially_supported, inconsistent, "
        "unsubstantiated, or insufficient_evidence) grounded strictly in verifiable filing citations."
    ),
)
def get_company_evaluations(
    ticker: str,
    assessment: Optional[str] = Query(
        None,
        description="Filter by assessment: 'supported', 'partially_supported', 'inconsistent', 'unsubstantiated', 'insufficient_evidence'",
    ),
    category: Optional[str] = Query(
        None,
        description="Filter by ESG category (e.g. 'inclusion', 'supply_chain', 'greenhouse_gas')",
    ),
    claim_type: Optional[str] = Query(
        None,
        description="Filter by claim type: 'target', 'achievement', 'current_state', 'policy', 'general'",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=500,
        description="Maximum number of evaluations to return",
    ),
    llm_service: LLMService = Depends(get_llm_service),
) -> CompanyEvaluationResponse:
    """Retrieve evaluations for all extracted sustainability claims."""
    response = llm_service.evaluate_company_filing(company_ticker=ticker)

    # Apply filters
    filtered_evals = response.evaluations
    if assessment:
        filtered_evals = [e for e in filtered_evals if e.assessment.value == assessment.lower()]
    if category:
        filtered_evals = [e for e in filtered_evals if e.category == category.lower()]
    if claim_type:
        filtered_evals = [e for e in filtered_evals if e.claim_type == claim_type.lower()]

    filtered_evals = filtered_evals[:limit]

    return CompanyEvaluationResponse(
        company=response.company,
        filing_accession_number=response.filing_accession_number,
        form_type=response.form_type,
        filing_date=response.filing_date,
        summary=response.summary,
        evaluations=filtered_evals,
        provider_mode=response.provider_mode,
        model_name=response.model_name,
    )
