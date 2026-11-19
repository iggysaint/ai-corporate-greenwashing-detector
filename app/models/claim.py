"""Claim domain models and API response schemas for sustainability claim extraction."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.company import Company
from app.models.filing import SECFiling


class ClaimType(str, Enum):
    """Controlled vocabulary for sustainability claim types."""

    TARGET = "target"
    ACHIEVEMENT = "achievement"
    CURRENT_STATE = "current_state"
    POLICY = "policy"
    GENERAL = "general"


class ClaimCategoryGroup(str, Enum):
    """High-level ESG pillar grouping."""

    ENVIRONMENTAL = "environmental"
    SOCIAL = "social"
    GOVERNANCE = "governance"
    OTHER = "other"


# Mapping from specific category to high-level pillar
CATEGORY_TO_GROUP: Dict[str, ClaimCategoryGroup] = {
    # Environmental
    "climate": ClaimCategoryGroup.ENVIRONMENTAL,
    "greenhouse_gas": ClaimCategoryGroup.ENVIRONMENTAL,
    "carbon": ClaimCategoryGroup.ENVIRONMENTAL,
    "emissions": ClaimCategoryGroup.ENVIRONMENTAL,
    "energy": ClaimCategoryGroup.ENVIRONMENTAL,
    "renewable_energy": ClaimCategoryGroup.ENVIRONMENTAL,
    "water": ClaimCategoryGroup.ENVIRONMENTAL,
    "waste": ClaimCategoryGroup.ENVIRONMENTAL,
    "recycling": ClaimCategoryGroup.ENVIRONMENTAL,
    "biodiversity": ClaimCategoryGroup.ENVIRONMENTAL,
    "environmental_management": ClaimCategoryGroup.ENVIRONMENTAL,
    "pollution": ClaimCategoryGroup.ENVIRONMENTAL,
    "circular_economy": ClaimCategoryGroup.ENVIRONMENTAL,
    "sustainability": ClaimCategoryGroup.ENVIRONMENTAL,
    # Social
    "employees": ClaimCategoryGroup.SOCIAL,
    "workforce": ClaimCategoryGroup.SOCIAL,
    "diversity": ClaimCategoryGroup.SOCIAL,
    "inclusion": ClaimCategoryGroup.SOCIAL,
    "health_and_safety": ClaimCategoryGroup.SOCIAL,
    "human_rights": ClaimCategoryGroup.SOCIAL,
    "labor": ClaimCategoryGroup.SOCIAL,
    "community": ClaimCategoryGroup.SOCIAL,
    "supply_chain": ClaimCategoryGroup.SOCIAL,
    # Governance
    "governance": ClaimCategoryGroup.GOVERNANCE,
    "board": ClaimCategoryGroup.GOVERNANCE,
    "ethics": ClaimCategoryGroup.GOVERNANCE,
    "compliance": ClaimCategoryGroup.GOVERNANCE,
    "risk_management": ClaimCategoryGroup.GOVERNANCE,
    "transparency": ClaimCategoryGroup.GOVERNANCE,
    "business_conduct": ClaimCategoryGroup.GOVERNANCE,
}


class SourceReference(BaseModel):
    """Source reference citation for repeated or corroborating claim occurrences."""

    source_type: str = Field("sec_10k", description="Type of document source (e.g. sec_10k)")
    source_title: str = Field(..., description="Document title or filing designation")
    source_url: str = Field(..., description="HTTPS URL to source document")
    filing_accession_number: str = Field(..., description="SEC accession number")
    section_id: str = Field(..., description="Section identifier (e.g. item_1, item_7)")
    section_title: str = Field(..., description="Section title where claim appears")
    source_excerpt: str = Field(..., description="Verbatim source excerpt containing the claim")
    source_location: str = Field(..., description="Human-readable section location")

    model_config = ConfigDict(str_strip_whitespace=True)


class Claim(BaseModel):
    """Structured representation of an extracted corporate sustainability claim."""

    claim_id: str = Field(..., description="Deterministic stable identifier derived from claim content")
    company_ticker: str = Field(..., description="Normalized company stock ticker symbol")
    company_name: str = Field(..., description="Official registered company title")
    claim_text: str = Field(..., description="Extracted affirmative claim statement")
    claim_type: str = Field(..., description="Claim type: target, achievement, current_state, policy, general")
    category: str = Field(..., description="Specific thematic ESG category")
    category_group: str = Field(..., description="High-level pillar: environmental, social, governance")
    source_type: str = Field("sec_10k", description="Source format/provenance")
    source_title: str = Field(..., description="Title of the source filing")
    source_url: str = Field(..., description="Direct HTTPS link to source document")
    filing_accession_number: str = Field(..., description="Unique SEC accession number")
    filing_date: str = Field(..., description="SEC filing date (YYYY-MM-DD)")
    report_date: Optional[str] = Field(None, description="Fiscal period end date (YYYY-MM-DD)")
    section_id: str = Field(..., description="Section identifier where claim originated")
    section_title: str = Field(..., description="Section title")
    source_excerpt: str = Field(..., description="Broader contextual excerpt from source document")
    source_location: str = Field(..., description="Human-readable document location")
    target_year: Optional[int] = Field(None, description="Explicit future target year if specified")
    baseline_year: Optional[int] = Field(None, description="Explicit baseline year if specified")
    metric: Optional[str] = Field(None, description="Identified metric subject of the claim")
    target_value: Optional[str] = Field(None, description="Quantitative value or threshold specified in claim")
    unit: Optional[str] = Field(None, description="Unit of measurement (e.g. percent, metric tons)")
    claim_date: Optional[str] = Field(None, description="Date associated with claim if distinguishable")
    extraction_method: str = Field("deterministic", description="Extraction method used: deterministic, llm, hybrid")
    confidence: str = Field("medium", description="Extraction confidence: high, medium, low")
    status: str = Field("candidate", description="Neutral extraction status: candidate, validated, rejected")
    additional_sources: List[SourceReference] = Field(
        default_factory=list,
        description="Additional sections where the same claim appears in the filing",
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "claim_id": "claim_aapl_0000320193_25_000079_1a2b3c4d5e6f",
                "company_ticker": "AAPL",
                "company_name": "Apple Inc.",
                "claim_text": "All corporate operations are powered by 100% renewable energy.",
                "claim_type": "achievement",
                "category": "renewable_energy",
                "category_group": "environmental",
                "source_type": "sec_10k",
                "source_title": "Apple Inc. Form 10-K",
                "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
                "filing_accession_number": "0000320193-25-000079",
                "filing_date": "2025-10-31",
                "report_date": "2025-09-27",
                "section_id": "item_1",
                "section_title": "Item 1. Business",
                "source_excerpt": "All corporate operations are powered by 100% renewable energy.",
                "source_location": "Item 1. Business",
                "target_year": None,
                "baseline_year": None,
                "metric": "renewable energy",
                "target_value": "100%",
                "unit": "percent",
                "claim_date": None,
                "extraction_method": "deterministic",
                "confidence": "high",
                "status": "validated",
                "additional_sources": [],
            }
        },
    )


# API Response Schemas
class CompanyClaimsResponse(BaseModel):
    """Structured response containing all extracted sustainability claims for a company."""

    company: Company = Field(..., description="Company identification metadata")
    filing: SECFiling = Field(..., description="Source annual filing metadata")
    total_claims: int = Field(..., description="Total number of structured claims returned")
    claims: List[Claim] = Field(..., description="List of structured sustainability claims")
    extraction_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata on extraction run (method, timestamp, filters)",
    )


class ClaimSummaryResponse(BaseModel):
    """Summary metrics of extracted sustainability claims by pillar, type, and category."""

    company: Company = Field(..., description="Company identification metadata")
    filing_accession_number: str = Field(..., description="Source SEC filing accession number")
    total_claims: int = Field(..., description="Total claims extracted")
    environmental_claims: int = Field(..., description="Count of environmental claims")
    social_claims: int = Field(..., description="Count of social claims")
    governance_claims: int = Field(..., description="Count of governance claims")
    target_claims: int = Field(..., description="Count of target/commitment claims")
    achievement_claims: int = Field(..., description="Count of achievement claims")
    policy_claims: int = Field(..., description="Count of policy/practice claims")
    current_state_claims: int = Field(..., description="Count of current state/performance claims")
    general_claims: int = Field(..., description="Count of general sustainability statements")
    by_category: Dict[str, int] = Field(default_factory=dict, description="Claim counts broken down by specific category")
    by_claim_type: Dict[str, int] = Field(default_factory=dict, description="Claim counts broken down by claim type")
