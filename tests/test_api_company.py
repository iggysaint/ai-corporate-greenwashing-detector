"""API tests for company identification and SEC filing discovery endpoints."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.sec_service import SECService, get_sec_service

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


@pytest.fixture
def mock_sec_service() -> SECService:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "company_tickers.json" in url:
            return httpx.Response(200, json=MOCK_TICKERS_JSON)
        if "CIK0000320193.json" in url:
            return httpx.Response(200, json=MOCK_AAPL_SUBMISSIONS)
        if "CIK0000999999.json" in url:
            return httpx.Response(200, json=MOCK_NO10K_SUBMISSIONS)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return SECService(client=client)


@pytest.fixture
def client(mock_sec_service: SECService):
    app.dependency_overrides[get_sec_service] = lambda: mock_sec_service
    yield TestClient(app)
    app.dependency_overrides.clear()


# 1. Company Identification Endpoints
def test_get_company_endpoint_success(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["company_name"] == "Apple Inc."
    assert data["cik"] == "0000320193"
    assert data["exchange"] == "Nasdaq"
    assert data["sic"] == "3571"
    assert data["sic_description"] == "Electronic Computers"


def test_get_company_endpoint_lowercase_normalization(client: TestClient) -> None:
    response = client.get("/api/v1/companies/aapl")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"


def test_get_company_endpoint_invalid_ticker(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL$$$")
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "invalid_ticker"
    assert "Invalid ticker format" in data["detail"]


def test_get_company_endpoint_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/companies/UNKNOWN")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "company_not_found"
    assert "not found in SEC EDGAR" in data["detail"]


# 2. Company Filings Endpoints
def test_get_company_filings_endpoint_success(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/filings")
    assert response.status_code == 200
    data = response.json()
    assert "company" in data
    assert data["company"]["ticker"] == "AAPL"
    assert "filings" in data
    assert data["total_count"] == 2
    assert len(data["filings"]) == 2
    assert data["filings"][0]["form_type"] == "10-K"
    assert data["filings"][0]["accession_number"] == "0000320193-25-000079"
    assert "filing_url" in data["filings"][0]


def test_get_company_filings_endpoint_invalid_ticker(client: TestClient) -> None:
    response = client.get("/api/v1/companies/INVALID_LONG_TICKER/filings")
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "invalid_ticker"


# 3. Latest Annual Filing Endpoint
def test_get_latest_filing_endpoint_success(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/filings/latest")
    assert response.status_code == 200
    data = response.json()
    assert "company" in data
    assert "filing" in data
    filing = data["filing"]
    assert filing["form_type"] == "10-K"
    assert filing["filing_date"] == "2025-10-31"
    assert filing["report_date"] == "2025-09-27"
    assert filing["fiscal_year"] == 2025
    assert filing["is_amendment"] is False
    assert filing["accession_number"] == "0000320193-25-000079"


def test_get_latest_filing_endpoint_no_10k_found(client: TestClient) -> None:
    response = client.get("/api/v1/companies/NO10K/filings/latest")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "filing_not_found"
    assert "No suitable annual filing" in data["detail"]


# 4. External SEC Error Handling on Endpoint
def test_get_company_sec_error(client: TestClient) -> None:
    def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"SEC Internal Error")

    err_service = SECService(client=httpx.Client(transport=httpx.MockTransport(error_handler)))
    app.dependency_overrides[get_sec_service] = lambda: err_service

    response = client.get("/api/v1/companies/AAPL")
    assert response.status_code == 502
    data = response.json()
    assert data["error"] == "sec_service_error"
