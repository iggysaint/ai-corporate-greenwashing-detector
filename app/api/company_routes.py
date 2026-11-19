"""API routes for company identification, filing discovery, 10-K document processing, and sustainability claims."""

from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.models.claim import Claim, ClaimSummaryResponse, CompanyClaimsResponse
from app.models.company import Company
from app.models.document import (
    DocumentMetadataResponse,
    DocumentSectionsResponse,
    RelevantPassagesResponse,
)
from app.models.filing import CompanyFilingsResponse, CompanyLatestFilingResponse
from app.services.claims_service import ClaimsService, get_claims_service
from app.services.document_service import DocumentService, get_document_service
from app.services.sec_service import SECService, get_sec_service

router = APIRouter(prefix="/companies", tags=["Companies"])


# 1. Company Identification
@router.get(
    "/{ticker}",
    response_model=Company,
    summary="Identify Company by Ticker",
    description="Retrieve verified SEC company identification and metadata for a stock ticker symbol.",
)
def get_company(
    ticker: str,
    sec_service: SECService = Depends(get_sec_service),
) -> Company:
    """Identify company and return structured SEC metadata."""
    return sec_service.get_company_by_ticker(ticker)


# 2. Filing Discovery
@router.get(
    "/{ticker}/filings",
    response_model=CompanyFilingsResponse,
    summary="Discover SEC Annual Filings",
    description="Discover relevant annual regulatory filings (10-K, 10-K/A) for a company from SEC EDGAR.",
)
def get_company_filings(
    ticker: str,
    sec_service: SECService = Depends(get_sec_service),
) -> CompanyFilingsResponse:
    """Retrieve list of relevant annual filings."""
    return sec_service.get_company_filings(ticker)


@router.get(
    "/{ticker}/filings/latest",
    response_model=CompanyLatestFilingResponse,
    summary="Get Latest Annual Filing",
    description="Select the most recent suitable annual filing (10-K or prevailing 10-K/A) for a company.",
)
def get_latest_annual_filing(
    ticker: str,
    sec_service: SECService = Depends(get_sec_service),
) -> CompanyLatestFilingResponse:
    """Retrieve the latest suitable annual filing."""
    return sec_service.get_latest_annual_filing(ticker)


# 3. Document Ingestion & Section Extraction
@router.get(
    "/{ticker}/filings/latest/document",
    response_model=DocumentMetadataResponse,
    summary="Retrieve Processed Document Metadata",
    description="Retrieve cleaned metadata, word counts, and detected sections for the latest 10-K annual filing.",
)
def get_latest_document_metadata(
    ticker: str,
    sec_service: SECService = Depends(get_sec_service),
    doc_service: DocumentService = Depends(get_document_service),
) -> DocumentMetadataResponse:
    """Retrieve document metadata and processing summary without enormous raw payload."""
    latest_resp = sec_service.get_latest_annual_filing(ticker)
    doc = doc_service.process_document(latest_resp.filing)

    return DocumentMetadataResponse(
        company=latest_resp.company,
        accession_number=doc.accession_number,
        form_type=doc.form_type,
        filing_date=doc.filing_date,
        report_date=doc.report_date,
        source_url=doc.source_url,
        title=doc.title,
        word_count=doc.word_count,
        character_count=len(doc.text),
        total_sections=len(doc.sections),
        detected_sections=[s.section_title for s in doc.sections],
    )


@router.get(
    "/{ticker}/filings/latest/document/sections",
    response_model=DocumentSectionsResponse,
    summary="Get Document Sections",
    description="Retrieve all detected structured 10-K sections (e.g. Business, Risk Factors, MD&A).",
)
def get_latest_document_sections(
    ticker: str,
    section_type: Optional[str] = Query(
        None,
        description="Filter sections by type (e.g. 'business', 'risk_factors', 'mda', 'financials')",
    ),
    sec_service: SECService = Depends(get_sec_service),
    doc_service: DocumentService = Depends(get_document_service),
) -> DocumentSectionsResponse:
    """Retrieve segmented sections from the latest annual filing."""
    latest_resp = sec_service.get_latest_annual_filing(ticker)
    doc = doc_service.process_document(latest_resp.filing)

    sections = doc.sections
    if section_type:
        norm_type = section_type.strip().lower()
        sections = [s for s in sections if s.section_type == norm_type]

    return DocumentSectionsResponse(
        company=latest_resp.company,
        accession_number=doc.accession_number,
        source_url=doc.source_url,
        total_sections=len(sections),
        sections=sections,
    )


@router.get(
    "/{ticker}/filings/latest/document/relevant-passages",
    response_model=RelevantPassagesResponse,
    summary="Extract Relevant ESG Passages",
    description="Retrieve traceable passages containing ESG-related keywords for downstream evidence analysis.",
)
def get_latest_relevant_passages(
    ticker: str,
    keywords: Optional[str] = Query(
        None,
        description="Optional comma-separated keyword list. Defaults to comprehensive ESG concepts.",
    ),
    max_passages: int = Query(
        50,
        ge=1,
        le=200,
        description="Maximum number of passages to return (1-200, default 50).",
    ),
    sec_service: SECService = Depends(get_sec_service),
    doc_service: DocumentService = Depends(get_document_service),
) -> RelevantPassagesResponse:
    """Retrieve contextual passages matching ESG keyword concepts."""
    latest_resp = sec_service.get_latest_annual_filing(ticker)
    doc = doc_service.process_document(latest_resp.filing)

    kw_list = [k.strip().lower() for k in keywords.split(",") if k.strip()] if keywords else None
    passages = doc_service.find_relevant_passages(
        document=doc,
        company_ticker=latest_resp.company.ticker,
        keywords=kw_list,
        max_passages=max_passages,
    )

    query_keywords = kw_list if kw_list else doc_service.settings.DEFAULT_ESG_KEYWORDS

    return RelevantPassagesResponse(
        company=latest_resp.company,
        accession_number=doc.accession_number,
        source_url=doc.source_url,
        query_keywords=query_keywords,
        total_passages=len(passages),
        passages=passages,
    )


# 4. Sustainability Claim Extraction (Phase 4)
@router.get(
    "/{ticker}/claims",
    response_model=CompanyClaimsResponse,
    summary="Extract Sustainability Claims",
    description="Extract structured corporate sustainability commitments, achievements, and policies from the latest 10-K.",
)
def get_company_claims(
    ticker: str,
    category: Optional[str] = Query(
        None,
        description="Filter claims by category or pillar (e.g. 'greenhouse_gas', 'renewable_energy', 'environmental')",
    ),
    claim_type: Optional[str] = Query(
        None,
        description="Filter claims by type: 'target', 'achievement', 'current_state', 'policy', 'general'",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=500,
        description="Maximum number of claims to return (1-500, default 50).",
    ),
    claims_service: ClaimsService = Depends(get_claims_service),
) -> CompanyClaimsResponse:
    """Retrieve structured sustainability claims extracted from the latest filing."""
    return claims_service.get_company_claims(
        ticker=ticker,
        category=category,
        claim_type=claim_type,
        limit=limit,
    )


@router.get(
    "/{ticker}/claims/summary",
    response_model=ClaimSummaryResponse,
    summary="Get Claims Summary Breakdown",
    description="Retrieve high-level claim counts categorized by ESG pillar (environmental, social, governance) and type.",
)
def get_claim_summary(
    ticker: str,
    claims_service: ClaimsService = Depends(get_claims_service),
) -> ClaimSummaryResponse:
    """Retrieve statistical summary breakdown of extracted claims."""
    return claims_service.get_claim_summary(ticker=ticker)


@router.get(
    "/{ticker}/claims/{claim_id}",
    response_model=Claim,
    summary="Get Individual Claim Record",
    description="Retrieve full details and complete source citations for an individual claim by its deterministic ID.",
)
def get_individual_claim(
    ticker: str,
    claim_id: str,
    claims_service: ClaimsService = Depends(get_claims_service),
) -> Claim:
    """Retrieve a single structured claim by ID."""
    return claims_service.get_claim_by_id(ticker=ticker, claim_id=claim_id)
