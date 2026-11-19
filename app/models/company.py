"""Company domain model."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Company(BaseModel):
    """Structured company identification and metadata from SEC EDGAR."""

    ticker: str = Field(..., description="Normalized company stock ticker symbol (e.g., AAPL)")
    company_name: str = Field(..., description="Official SEC registered company title")
    cik: str = Field(..., description="10-digit Central Index Key (CIK) with leading zeros")
    exchange: Optional[str] = Field(None, description="Primary trading exchange if available")
    sic: Optional[str] = Field(None, description="Standard Industrial Classification code")
    sic_description: Optional[str] = Field(None, description="SIC category description")

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "cik": "0000320193",
                "exchange": "Nasdaq",
                "sic": "3571",
                "sic_description": "Electronic Computers",
            }
        },
    )

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        """Ensure ticker is uppercase and stripped."""
        return value.strip().upper()

    @field_validator("cik")
    @classmethod
    def validate_cik(cls, value: str) -> str:
        """Ensure CIK is formatted as 10-digit string with leading zeros."""
        clean = value.strip()
        if clean.isdigit():
            return clean.zfill(10)
        return clean
