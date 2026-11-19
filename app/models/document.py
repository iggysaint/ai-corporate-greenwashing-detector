"""Document domain models and API response schemas for SEC filing processing."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.company import Company


class DocumentSection(BaseModel):
    """Structured section extracted from an SEC 10-K regulatory filing."""

    section_id: str = Field(..., description="Normalized section identifier (e.g. 'item_1', 'item_1a')")
    section_title: str = Field(..., description="Heading or title of the section (e.g. 'Item 1. Business')")
    section_type: str = Field(
        ...,
        description="Standardized section category ('business', 'risk_factors', 'mda', 'financials', 'other')",
    )
    text: str = Field(..., description="Cleaned readable text content of the section")
    start_position: int = Field(..., description="Starting character index in full normalized document text")
    end_position: int = Field(..., description="Ending character index in full normalized document text")
    word_count: int = Field(..., description="Approximate word count of the section content")

    model_config = ConfigDict(str_strip_whitespace=True)


class RelevantPassage(BaseModel):
    """Contextual passage matching targeted keywords with full source traceability."""

    passage_id: str = Field(..., description="Unique deterministic identifier for the passage")
    company_ticker: str = Field(..., description="Stock ticker symbol of the company")
    accession_number: str = Field(..., description="SEC accession number of the source filing")
    source_url: str = Field(..., description="Direct HTTPS URL to the source filing on SEC EDGAR")
    section_id: str = Field(..., description="Section identifier where the passage was discovered")
    section_title: str = Field(..., description="Heading of the section containing the passage")
    text: str = Field(..., description="Contextual passage text surrounding the matched keyword")
    matched_keywords: List[str] = Field(..., description="List of keywords identified within this passage")
    approximate_position: int = Field(..., description="Character offset within the containing section")

    model_config = ConfigDict(str_strip_whitespace=True)


class Document(BaseModel):
    """Full structured representation of a retrieved and parsed SEC 10-K filing."""

    accession_number: str = Field(..., description="SEC accession number identifier")
    form_type: str = Field(..., description="Form type designation (e.g. '10-K', '10-K/A')")
    filing_date: str = Field(..., description="Filing submission date (YYYY-MM-DD)")
    report_date: Optional[str] = Field(None, description="Fiscal period end date (YYYY-MM-DD)")
    source_url: str = Field(..., description="Direct HTTPS URL to primary document on SEC EDGAR")
    title: Optional[str] = Field(None, description="Document title extracted from header or filing")
    text: str = Field(..., description="Complete normalized cleaned plain text of the document")
    word_count: int = Field(..., description="Total word count of document text")
    sections: List[DocumentSection] = Field(default_factory=list, description="List of detected document sections")

    model_config = ConfigDict(str_strip_whitespace=True)


# API Response Schemas
class DocumentMetadataResponse(BaseModel):
    """Document metadata and processing summary without returning full raw text payload."""

    company: Company = Field(..., description="Company identification metadata")
    accession_number: str = Field(..., description="SEC accession number")
    form_type: str = Field(..., description="Form type (10-K or 10-K/A)")
    filing_date: str = Field(..., description="Filing date")
    report_date: Optional[str] = Field(None, description="Report date")
    source_url: str = Field(..., description="SEC source URL")
    title: Optional[str] = Field(None, description="Document title")
    word_count: int = Field(..., description="Total words in cleaned text")
    character_count: int = Field(..., description="Total characters in cleaned text")
    total_sections: int = Field(..., description="Total structured sections detected")
    detected_sections: List[str] = Field(..., description="List of detected section titles")


class DocumentSectionsResponse(BaseModel):
    """Structured response containing all detected sections for a filing."""

    company: Company = Field(..., description="Company identification metadata")
    accession_number: str = Field(..., description="SEC accession number")
    source_url: str = Field(..., description="SEC source URL")
    total_sections: int = Field(..., description="Number of sections returned")
    sections: List[DocumentSection] = Field(..., description="List of structured sections")


class RelevantPassagesResponse(BaseModel):
    """Structured response containing traceable evidence passages matching keyword concepts."""

    company: Company = Field(..., description="Company identification metadata")
    accession_number: str = Field(..., description="SEC accession number")
    source_url: str = Field(..., description="SEC source URL")
    query_keywords: List[str] = Field(..., description="Keywords searched")
    total_passages: int = Field(..., description="Total passages identified")
    passages: List[RelevantPassage] = Field(..., description="List of traceable evidence passages")
