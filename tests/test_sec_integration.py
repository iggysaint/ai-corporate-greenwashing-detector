"""Optional live integration tests querying real SEC EDGAR infrastructure.

Run specifically with:
    pytest -m integration -v
"""

import os
import pytest
import httpx

from app.models.company import Company
from app.services.sec_service import SECService
from app.utils.config import get_settings


@pytest.mark.integration
def test_live_sec_apple_identification() -> None:
    """Live verification: Identify Apple Inc. (AAPL) from SEC EDGAR."""
    settings = get_settings()
    service = SECService(settings=settings)

    try:
        company = service.get_company_by_ticker("AAPL")
        assert isinstance(company, Company)
        assert company.ticker == "AAPL"
        assert company.cik == "0000320193"
        assert "Apple" in company.company_name
        assert company.sic == "3571"
    except httpx.HTTPError as exc:
        pytest.skip(f"SEC EDGAR live service temporarily unreachable: {exc}")
    finally:
        service.close()


@pytest.mark.integration
def test_live_sec_apple_filings_discovery() -> None:
    """Live verification: Discover AAPL 10-K filings and latest annual filing."""
    settings = get_settings()
    service = SECService(settings=settings)

    try:
        filings_resp = service.get_company_filings("AAPL")
        assert filings_resp.company.ticker == "AAPL"
        assert filings_resp.total_count > 0

        latest_resp = service.get_latest_annual_filing("AAPL")
        assert latest_resp.filing.form_type in ("10-K", "10-K/A")
        assert latest_resp.filing.filing_url.startswith("https://www.sec.gov/Archives/edgar/data/320193/")
        assert latest_resp.filing.fiscal_year is not None
        assert latest_resp.filing.fiscal_year >= 2023
    except httpx.HTTPError as exc:
        pytest.skip(f"SEC EDGAR live service temporarily unreachable: {exc}")
    finally:
        service.close()


@pytest.mark.integration
def test_live_sec_apple_document_processing() -> None:
    """Live verification: Retrieve, clean, segment, and extract ESG passages from Apple 10-K."""
    from app.services.document_service import DocumentService

    settings = get_settings()
    sec_service = SECService(settings=settings)
    doc_service = DocumentService(settings=settings)

    try:
        # 1. Identify Apple & 2. Find latest filing
        latest_resp = sec_service.get_latest_annual_filing("AAPL")
        filing = latest_resp.filing

        # 3. Retrieve & 4. Parse & 5. Non-empty cleaned text & 6. Identify sections
        doc = doc_service.process_document(filing)
        assert doc.accession_number == filing.accession_number
        assert len(doc.text) > 10000
        assert doc.word_count > 2000
        assert len(doc.sections) >= 3

        # 7. Find at least some ESG-related passages
        passages = doc_service.find_relevant_passages(
            document=doc,
            company_ticker="AAPL",
            keywords=["climate", "employees", "compliance", "governance"],
            max_passages=10,
        )
        assert len(passages) > 0
        for p in passages:
            assert p.company_ticker == "AAPL"
            assert p.accession_number == filing.accession_number
            assert len(p.matched_keywords) > 0
    except httpx.HTTPError as exc:
        pytest.skip(f"SEC EDGAR live service temporarily unreachable: {exc}")
    finally:
        sec_service.close()
        doc_service.close()
