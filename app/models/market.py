"""Multi-market domain models for cross-exchange company and document support.

Extends the application to support multiple stock exchanges and regulatory
document sources beyond SEC EDGAR. Each market adapter produces standardized
MarketDocument records that feed into the shared claim/evidence/evaluation pipeline.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.evaluation import ClaimEvaluation, EvaluationSummary


class MarketIdentifier(str, Enum):
    """Supported market/exchange identifiers."""

    US_SEC = "us_sec"
    """United States — SEC EDGAR regulatory filings."""

    GH_GSE = "gh_gse"
    """Ghana — Ghana Stock Exchange listed companies."""


class DocumentSourceType(str, Enum):
    """Source type of the retrieved corporate document."""

    SEC_10K = "sec_10k"
    """US SEC annual filing (10-K / 10-K/A)."""

    ANNUAL_REPORT = "annual_report"
    """Published annual report (non-SEC jurisdiction)."""

    SUSTAINABILITY_REPORT = "sustainability_report"
    """Standalone sustainability or ESG report."""

    INTEGRATED_REPORT = "integrated_report"
    """Integrated report combining financial and sustainability information."""

    INVESTOR_PRESENTATION = "investor_presentation"
    """Investor-facing presentation or factsheet."""

    UNKNOWN = "unknown"
    """Unclassified document type."""


class GSECompany(BaseModel):
    """Company listed on the Ghana Stock Exchange.

    Fields align with data available from public GSE APIs (e.g., Kwayisi API).
    """

    ticker: str = Field(..., description="GSE ticker symbol (e.g., MTNGH)")
    company_name: str = Field(..., description="Full registered company name")
    market: MarketIdentifier = Field(
        default=MarketIdentifier.GH_GSE,
        description="Market identifier",
    )
    isin: Optional[str] = Field(None, description="International Securities Identification Number")
    sector: Optional[str] = Field(None, description="Industry sector classification")
    industry: Optional[str] = Field(None, description="Industry sub-classification")
    currency: str = Field(default="GHS", description="Trading currency")
    shares_outstanding: Optional[int] = Field(None, description="Total shares outstanding")
    market_cap: Optional[float] = Field(None, description="Market capitalization in trading currency")
    year_listed: Optional[int] = Field(None, description="Year the company was listed on GSE")
    website: Optional[str] = Field(None, description="Company corporate website URL")

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "ticker": "MTNGH",
                "company_name": "MTN Ghana Ltd",
                "market": "gh_gse",
                "sector": "Telecommunications",
                "currency": "GHS",
            }
        },
    )


class MarketDocument(BaseModel):
    """A corporate document retrieved from any supported market source.

    This is the market-agnostic representation that feeds into the shared
    DocumentService → ClaimsService → EvidenceService pipeline.
    """

    document_id: str = Field(..., description="Unique document identifier")
    company_ticker: str = Field(..., description="Company ticker symbol")
    company_name: str = Field(..., description="Company name")
    market: MarketIdentifier = Field(..., description="Source market identifier")
    source_type: DocumentSourceType = Field(..., description="Document source classification")
    title: str = Field(..., description="Document title or filename")
    reporting_period: Optional[str] = Field(None, description="Reporting period (e.g., '2024', 'FY2024')")
    publication_date: Optional[str] = Field(None, description="Publication or filing date (YYYY-MM-DD)")
    source_url: Optional[str] = Field(None, description="Original document URL")
    retrieval_status: str = Field(default="pending", description="Retrieval status: pending, retrieved, failed, unavailable")
    text_content: Optional[str] = Field(None, description="Extracted plain text content")
    text_length: Optional[int] = Field(None, description="Character length of extracted text")
    word_count: Optional[int] = Field(None, description="Word count of extracted text")
    page_count: Optional[int] = Field(None, description="Number of pages (for PDFs)")
    format: str = Field(default="unknown", description="Original document format: html, pdf, text, unknown")
    error_message: Optional[str] = Field(None, description="Error message if retrieval or parsing failed")

    model_config = ConfigDict(str_strip_whitespace=True)


class GSECompanyListResponse(BaseModel):
    """Response containing a list of GSE-listed companies."""

    companies: List[GSECompany] = Field(..., description="List of GSE-listed companies")
    total_count: int = Field(..., description="Total number of companies")
    market: MarketIdentifier = Field(
        default=MarketIdentifier.GH_GSE,
        description="Market identifier",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class GSECompanyDetailResponse(BaseModel):
    """Detailed response for a single GSE company."""

    company: GSECompany = Field(..., description="Company information")
    documents: List[MarketDocument] = Field(
        default_factory=list,
        description="Available corporate documents",
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class GSEDocumentResponse(BaseModel):
    """Response for a GSE company's document retrieval result."""

    company: GSECompany = Field(..., description="Company information")
    document: MarketDocument = Field(..., description="Retrieved document metadata and content")

    model_config = ConfigDict(str_strip_whitespace=True)


class GSEAnalysisResponse(BaseModel):
    """Aggregate response evaluating sustainability claims for a GSE company document."""

    company: GSECompany = Field(..., description="Company identification metadata")
    document: MarketDocument = Field(..., description="Document evaluated")
    total_claims_extracted: int = Field(0, description="Total sustainability claims extracted")
    evaluations: List[ClaimEvaluation] = Field(default_factory=list, description="Evaluated claims")
    summary: EvaluationSummary = Field(..., description="Evaluation summary breakdown")
    provider_mode: str = Field(..., description="Active execution mode: 'llm' or 'rule_based'")

    model_config = ConfigDict(str_strip_whitespace=True)
