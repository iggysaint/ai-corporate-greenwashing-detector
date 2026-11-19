"""Unit tests for SECService with deterministic mocked SEC responses."""

import httpx
import pytest

from app.models.company import Company
from app.services.sec_service import (
    SECService,
    normalize_and_validate_ticker,
)
from app.utils.config import Settings
from app.utils.exceptions import (
    CompanyNotFoundError,
    FilingNotFoundError,
    SECConnectionError,
    SECRateLimitError,
    SECServiceError,
    TickerValidationError,
)

# Mock SEC Data
MOCK_TICKERS_JSON = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
    "2": {"cik_str": 999999, "ticker": "NO10K", "title": "No Filings Corp"},
}

MOCK_AAPL_SUBMISSIONS = {
    "cik": "0000320193",
    "name": "Apple Inc.",
    "tickers": ["AAPL"],
    "exchanges": ["Nasdaq"],
    "sic": "3571",
    "sicDescription": "Electronic Computers",
    "filings": {
        "recent": {
            "form": ["4", "10-K", "10-Q", "10-K"],
            "filingDate": ["2025-11-05", "2025-10-31", "2025-08-01", "2024-11-01"],
            "reportDate": ["2025-11-05", "2025-09-27", "2025-06-28", "2024-09-28"],
            "accessionNumber": [
                "0000320193-25-000085",
                "0000320193-25-000079",
                "0000320193-25-000060",
                "0000320193-24-000106",
            ],
            "primaryDocument": [
                "form4.xml",
                "aapl-20250927.htm",
                "aapl-20250628.htm",
                "aapl-20240928.htm",
            ],
        }
    },
}

MOCK_MSFT_SUBMISSIONS = {
    "cik": "0000789019",
    "name": "MICROSOFT CORP",
    "tickers": ["MSFT"],
    "exchanges": ["Nasdaq"],
    "sic": "7372",
    "sicDescription": "Services-Prepackaged Software",
    "filings": {
        "recent": {
            "form": ["10-K/A", "10-K"],
            "filingDate": ["2024-11-15", "2024-10-25"],
            "reportDate": ["2024-09-30", "2024-09-30"],
            "accessionNumber": ["0000789019-24-000099", "0000789019-24-000088"],
            "primaryDocument": ["msft-20240930a.htm", "msft-20240930.htm"],
        }
    },
}

MOCK_NO10K_SUBMISSIONS = {
    "cik": "0000999999",
    "name": "No Filings Corp",
    "tickers": ["NO10K"],
    "exchanges": ["NYSE"],
    "sic": "9999",
    "sicDescription": "Non-classifiable",
    "filings": {
        "recent": {
            "form": ["8-K", "4"],
            "filingDate": ["2025-01-10", "2025-01-05"],
            "reportDate": ["2025-01-10", "2025-01-05"],
            "accessionNumber": ["0000999999-25-000002", "0000999999-25-000001"],
            "primaryDocument": ["form8k.htm", "form4.xml"],
        }
    },
}


def create_mock_transport(handler) -> httpx.Client:
    """Helper creating an httpx.Client using a mock transport handler."""
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


# 1. Ticker Normalization and Validation Tests
def test_normalize_and_validate_ticker_valid() -> None:
    assert normalize_and_validate_ticker("AAPL") == "AAPL"
    assert normalize_and_validate_ticker("msft") == "MSFT"
    assert normalize_and_validate_ticker("brk.a") == "BRK.A"
    assert normalize_and_validate_ticker("bf-b") == "BF-B"


def test_normalize_and_validate_ticker_empty() -> None:
    with pytest.raises(TickerValidationError, match="cannot be empty"):
        normalize_and_validate_ticker("")

    with pytest.raises(TickerValidationError, match="cannot be empty"):
        normalize_and_validate_ticker("   ")


def test_normalize_and_validate_ticker_invalid_format() -> None:
    with pytest.raises(TickerValidationError, match="Invalid ticker format"):
        normalize_and_validate_ticker("AAPL$")

    with pytest.raises(TickerValidationError, match="Invalid ticker format"):
        normalize_and_validate_ticker("VERYLONGTICKERNAME")

    with pytest.raises(TickerValidationError, match="Invalid ticker format"):
        normalize_and_validate_ticker("MS FT")


# 2. Company Identification Tests
def test_get_company_by_ticker_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "company_tickers.json" in url:
            return httpx.Response(200, json=MOCK_TICKERS_JSON)
        if "CIK0000320193.json" in url:
            return httpx.Response(200, json=MOCK_AAPL_SUBMISSIONS)
        return httpx.Response(404)

    client = create_mock_transport(handler)
    service = SECService(client=client)

    # Test lowercase normalization in retrieval
    company = service.get_company_by_ticker("aapl")
    assert isinstance(company, Company)
    assert company.ticker == "AAPL"
    assert company.cik == "0000320193"
    assert company.company_name == "Apple Inc."
    assert company.exchange == "Nasdaq"
    assert company.sic == "3571"
    assert company.sic_description == "Electronic Computers"


def test_get_company_by_ticker_unknown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=MOCK_TICKERS_JSON)

    client = create_mock_transport(handler)
    service = SECService(client=client)

    with pytest.raises(CompanyNotFoundError, match="was not found in SEC EDGAR records"):
        service.get_company_by_ticker("UNKNOWN")


def test_get_company_by_ticker_malformed_tickers_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"invalid json")

    client = create_mock_transport(handler)
    service = SECService(client=client)

    with pytest.raises(SECServiceError, match="Malformed JSON response"):
        service.get_company_by_ticker("AAPL")


def test_get_company_by_ticker_sec_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout connecting to SEC")

    client = create_mock_transport(handler)
    service = SECService(client=client)

    with pytest.raises(SECConnectionError, match="timeout"):
        service.get_company_by_ticker("AAPL")


# 3. Filing Discovery & Latest 10-K Tests
def test_get_company_filings_with_10k() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "company_tickers.json" in url:
            return httpx.Response(200, json=MOCK_TICKERS_JSON)
        if "CIK0000320193.json" in url:
            return httpx.Response(200, json=MOCK_AAPL_SUBMISSIONS)
        return httpx.Response(404)

    client = create_mock_transport(handler)
    service = SECService(client=client)

    resp = service.get_company_filings("AAPL")
    assert resp.company.ticker == "AAPL"
    assert resp.total_count == 2
    assert len(resp.filings) == 2
    # Non-annual forms (4, 10-Q) should be excluded
    for filing in resp.filings:
        assert filing.form_type in ("10-K", "10-K/A")
        assert filing.filing_url.startswith("https://www.sec.gov/Archives/edgar/data/320193/")
        assert filing.filing_index_url.endswith("-index.htm")


def test_get_company_filings_with_10ka_amendment() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "company_tickers.json" in url:
            return httpx.Response(200, json=MOCK_TICKERS_JSON)
        if "CIK0000789019.json" in url:
            return httpx.Response(200, json=MOCK_MSFT_SUBMISSIONS)
        return httpx.Response(404)

    client = create_mock_transport(handler)
    service = SECService(client=client)

    resp = service.get_company_filings("MSFT")
    assert resp.total_count == 2
    amendment = next(f for f in resp.filings if f.form_type == "10-K/A")
    assert amendment.is_amendment is True
    assert amendment.accession_number == "0000789019-24-000099"


def test_select_latest_annual_filing_prefers_amendment_for_latest_period() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "company_tickers.json" in url:
            return httpx.Response(200, json=MOCK_TICKERS_JSON)
        if "CIK0000789019.json" in url:
            return httpx.Response(200, json=MOCK_MSFT_SUBMISSIONS)
        return httpx.Response(404)

    client = create_mock_transport(handler)
    service = SECService(client=client)

    latest_resp = service.get_latest_annual_filing("MSFT")
    # For reporting date 2024-09-30, 10-K/A was filed on 2024-11-15 after 10-K on 2024-10-25
    assert latest_resp.filing.form_type == "10-K/A"
    assert latest_resp.filing.is_amendment is True
    assert latest_resp.filing.filing_date == "2024-11-15"
    assert latest_resp.filing.report_date == "2024-09-30"


def test_select_latest_annual_filing_standard_10k() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "company_tickers.json" in url:
            return httpx.Response(200, json=MOCK_TICKERS_JSON)
        if "CIK0000320193.json" in url:
            return httpx.Response(200, json=MOCK_AAPL_SUBMISSIONS)
        return httpx.Response(404)

    client = create_mock_transport(handler)
    service = SECService(client=client)

    latest_resp = service.get_latest_annual_filing("AAPL")
    assert latest_resp.filing.form_type == "10-K"
    assert latest_resp.filing.filing_date == "2025-10-31"
    assert latest_resp.filing.report_date == "2025-09-27"
    assert latest_resp.filing.fiscal_year == 2025
    assert latest_resp.filing.is_amendment is False


def test_select_latest_annual_filing_none_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "company_tickers.json" in url:
            return httpx.Response(200, json=MOCK_TICKERS_JSON)
        if "CIK0000999999.json" in url:
            return httpx.Response(200, json=MOCK_NO10K_SUBMISSIONS)
        return httpx.Response(404)

    client = create_mock_transport(handler)
    service = SECService(client=client)

    with pytest.raises(FilingNotFoundError, match="No suitable annual filing"):
        service.get_latest_annual_filing("NO10K")


def test_get_company_filings_malformed_metadata() -> None:
    malformed_submissions = {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "tickers": ["AAPL"],
        "filings": {
            "recent": {
                "form": "not-a-list",
                "accessionNumber": "not-a-list",
            }
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "company_tickers.json" in url:
            return httpx.Response(200, json=MOCK_TICKERS_JSON)
        if "CIK0000320193.json" in url:
            return httpx.Response(200, json=malformed_submissions)
        return httpx.Response(404)

    client = create_mock_transport(handler)
    service = SECService(client=client)

    with pytest.raises(SECServiceError, match="Malformed filing metadata"):
        service.get_company_filings("AAPL")


def test_sec_rate_limiting_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, content=b"Too Many Requests")

    client = create_mock_transport(handler)
    service = SECService(client=client)

    with pytest.raises(SECRateLimitError, match="rate limit exceeded"):
        service.load_ticker_mapping()


def test_url_builders() -> None:
    filing_url = SECService.build_filing_url(
        cik="0000320193",
        accession_number="0000320193-25-000079",
        primary_document="aapl-20250927.htm",
    )
    assert filing_url == "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"

    index_url = SECService.build_filing_index_url(
        cik="0000320193",
        accession_number="0000320193-25-000079",
    )
    assert index_url == "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/0000320193-25-000079-index.htm"
