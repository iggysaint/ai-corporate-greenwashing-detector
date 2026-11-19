"""API routes for Ghana Stock Exchange (GSE) company discovery and document retrieval.

Provides endpoints for:
- Listing all GSE-listed companies
- Looking up a specific GSE company by ticker
- Discovering available documents for a GSE company
- Retrieving and processing a document from a URL
- Retrieving Ghana-specific ESG keywords
"""

from typing import List, Optional
from fastapi import APIRouter, Query

from app.models.market import (
    DocumentSourceType,
    GSEAnalysisResponse,
    GSECompanyDetailResponse,
    GSECompanyListResponse,
    GSEDocumentResponse,
    MarketDocument,
)
from app.services.gse_service import GSEService, get_gse_service

router = APIRouter(prefix="/gse", tags=["Ghana Stock Exchange"])


@router.get(
    "/companies",
    response_model=GSECompanyListResponse,
    summary="List all GSE-listed companies",
    description="Retrieve all companies currently listed on the Ghana Stock Exchange.",
)
def get_gse_companies() -> GSECompanyListResponse:
    """Return all GSE-listed companies from the Kwayisi API."""
    service = get_gse_service()
    return service.get_listed_companies()


@router.get(
    "/companies/{ticker}",
    response_model=GSECompanyDetailResponse,
    summary="Get GSE company details and available documents",
    description="Look up a GSE company by ticker and discover available corporate documents.",
)
def get_gse_company_detail(ticker: str) -> GSECompanyDetailResponse:
    """Return company details and available document stubs for a GSE ticker."""
    service = get_gse_service()
    return service.discover_company_documents(ticker)


@router.post(
    "/companies/{ticker}/documents",
    response_model=GSEDocumentResponse,
    summary="Retrieve and process a GSE company document",
    description=(
        "Download and extract text from a corporate document (HTML or PDF) at the given URL. "
        "Returns the extracted content for downstream analysis."
    ),
)
def retrieve_gse_document(
    ticker: str,
    source_url: str = Query(..., description="Direct URL to the corporate document"),
    source_type: DocumentSourceType = Query(
        DocumentSourceType.ANNUAL_REPORT,
        description="Type of document being retrieved",
    ),
    reporting_period: Optional[str] = Query(None, description="Reporting period (e.g., '2024')"),
) -> GSEDocumentResponse:
    """Retrieve a document from a URL and extract its text content."""
    service = get_gse_service()
    company = service.get_company_by_ticker(ticker)
    document = service.retrieve_document_from_url(
        ticker=ticker,
        source_url=source_url,
        source_type=source_type,
        reporting_period=reporting_period,
    )
    return GSEDocumentResponse(company=company, document=document)


@router.post(
    "/companies/{ticker}/analyze",
    response_model=GSEAnalysisResponse,
    summary="Analyze sustainability claims in a GSE company document",
    description=(
        "Execute end-to-end sustainability claim extraction, evidence retrieval, "
        "and consistency evaluation for a GSE company document. If source_url is omitted, "
        "the latest verified public report is automatically selected."
    ),
)
def analyze_gse_document(
    ticker: str,
    source_url: Optional[str] = Query(None, description="Optional direct URL to corporate document"),
    source_type: DocumentSourceType = Query(
        DocumentSourceType.ANNUAL_REPORT,
        description="Type of document",
    ),
    reporting_period: Optional[str] = Query(None, description="Reporting period (e.g. '2024')"),
) -> GSEAnalysisResponse:
    """Execute end-to-end analysis on a GSE document."""
    service = get_gse_service()
    return service.analyze_company_document(
        ticker=ticker,
        source_url=source_url,
        source_type=source_type,
        reporting_period=reporting_period,
    )


@router.get(
    "/esg-keywords",
    response_model=List[str],
    summary="Get Ghana-specific ESG keywords",
    description="Return ESG keywords relevant to Ghanaian corporate sustainability disclosures.",
)
def get_ghana_esg_keywords(
    sector: Optional[str] = Query(None, description="Filter keywords by sector"),
) -> List[str]:
    """Return Ghana-specific ESG keywords, optionally filtered by sector."""
    return GSEService.get_ghana_esg_keywords(sector=sector)
