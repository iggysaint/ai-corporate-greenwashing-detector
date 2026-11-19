"""SEC Filing domain models and response schemas."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.company import Company


class SECFiling(BaseModel):
    """Metadata representing an SEC regulatory filing."""

    form_type: str = Field(..., description="SEC form type (e.g., '10-K', '10-K/A')")
    filing_date: str = Field(..., description="Filing submission date in YYYY-MM-DD format")
    report_date: Optional[str] = Field(None, description="Fiscal period end date in YYYY-MM-DD format")
    accession_number: str = Field(..., description="Unique SEC accession number identifier")
    primary_document: str = Field(..., description="Primary filing document filename")
    filing_url: str = Field(..., description="Direct HTTPS link to the primary filing document on SEC EDGAR")
    filing_index_url: Optional[str] = Field(None, description="HTTPS link to the SEC filing folder index")
    fiscal_year: Optional[int] = Field(None, description="Fiscal year extracted from the filing/report date")
    is_amendment: bool = Field(False, description="Indicates whether this filing is an amendment (e.g., 10-K/A)")

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "form_type": "10-K",
                "filing_date": "2025-10-31",
                "report_date": "2025-09-27",
                "accession_number": "0000320193-25-000079",
                "primary_document": "aapl-20250927.htm",
                "filing_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
                "filing_index_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/0000320193-25-000079-index.htm",
                "fiscal_year": 2025,
                "is_amendment": False,
            }
        },
    )


class CompanyFilingsResponse(BaseModel):
    """Structured response containing company metadata and a list of SEC filings."""

    company: Company = Field(..., description="Company identification metadata")
    filings: List[SECFiling] = Field(..., description="List of relevant annual filings")
    total_count: int = Field(..., description="Total count of discovered filings")


class CompanyLatestFilingResponse(BaseModel):
    """Structured response containing company metadata and its latest suitable annual filing."""

    company: Company = Field(..., description="Company identification metadata")
    filing: SECFiling = Field(..., description="Latest suitable 10-K or 10-K/A filing")
