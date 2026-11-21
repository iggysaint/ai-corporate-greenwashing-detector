"""API routes for Phase 8 ESG Integrity Scoring Engine.

Provides endpoints for:
- Retrieving the primary ESG Integrity Score for a company
- Retrieving the detailed transparent scoring breakdown across all claims and pillars
- Retrieving scoring history from in-memory evaluations
"""

from fastapi import APIRouter, Depends

from app.models.market import MarketIdentifier
from app.models.scoring import (
    ESGIntegrityScoreResponse,
    ESGScoreBreakdownResponse,
    ESGScoreHistoryResponse,
)
from app.services.scoring_service import ScoringService, get_scoring_service

router = APIRouter(prefix="/companies", tags=["ESG Integrity Scoring"])


@router.get(
    "/{ticker}/score",
    response_model=ESGIntegrityScoreResponse,
    summary="Get Company ESG Integrity Score",
    description=(
        "Retrieve the ESG Integrity Score (0-100) evaluating the credibility and evidence "
        "substantiation of a company's disclosed sustainability claims based on regulatory filings. "
        "This score evaluates disclosure integrity based on available evidence, NOT overall environmental impact."
    ),
)
def get_company_score(
    ticker: str,
    scoring_service: ScoringService = Depends(get_scoring_service),
) -> ESGIntegrityScoreResponse:
    """Retrieve the primary ESG Integrity Score response for a company."""
    return scoring_service.get_company_score(ticker=ticker, market=MarketIdentifier.US_SEC)


@router.get(
    "/{ticker}/score/breakdown",
    response_model=ESGScoreBreakdownResponse,
    summary="Get Detailed ESG Integrity Score Breakdown",
    description=(
        "Retrieve the full transparent calculation breakdown of the ESG Integrity Score, "
        "including pillar scores (Environmental, Social, Governance), claim-level materiality weights, "
        "evidence quality factors, and traceable citations."
    ),
)
def get_company_score_breakdown(
    ticker: str,
    scoring_service: ScoringService = Depends(get_scoring_service),
) -> ESGScoreBreakdownResponse:
    """Retrieve full transparent score breakdown for a company."""
    return scoring_service.get_company_score_breakdown(ticker=ticker, market=MarketIdentifier.US_SEC)


@router.get(
    "/{ticker}/score/history",
    response_model=ESGScoreHistoryResponse,
    summary="Get Company ESG Integrity Score History",
    description=(
        "Return only ESG Integrity assessments actually computed by this server process for the company "
        "(in-memory; no database in this phase; cleared on restart). Historical scores are never estimated "
        "or fabricated. Returns zero records if no assessment has been run yet."
    ),
)
def get_company_score_history(
    ticker: str,
    scoring_service: ScoringService = Depends(get_scoring_service),
) -> ESGScoreHistoryResponse:
    """Retrieve historical scoring runs for a company."""
    return scoring_service.get_company_score_history(ticker=ticker, market=MarketIdentifier.US_SEC)
