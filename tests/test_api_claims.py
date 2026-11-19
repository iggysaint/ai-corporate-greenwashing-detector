"""API tests for sustainability claims extraction endpoints."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.claims_service import ClaimsService, get_claims_service
from app.services.document_service import DocumentService, get_document_service
from app.services.sec_service import SECService, get_sec_service

MOCK_TICKERS_JSON = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
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
            "form": ["10-K"],
            "filingDate": ["2025-10-31"],
            "reportDate": ["2025-09-27"],
            "accessionNumber": ["0000320193-25-000079"],
            "primaryDocument": ["aapl-20250927.htm"],
        }
    },
}

MOCK_10K_HTML = """
<!DOCTYPE html>
<html>
<head><title>Apple Inc. Form 10-K</title></head>
<body>
    <h1>ITEM 1. BUSINESS</h1>
    <p>All corporate operations are powered by 100% renewable energy across all facilities worldwide.
    We aim to achieve net-zero emissions across our entire supply chain by 2030 compared with our 2020 baseline.
    We maintain a supplier code of conduct that addresses environmental standards and fair labor.</p>

    <h1>ITEM 1A. RISK FACTORS</h1>
    <p>Climate change and extreme weather events could materially adversely affect our global logistics.</p>

    <h1>ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS</h1>
    <p>We achieved a 30% reduction in carbon emissions across corporate facilities.
    Our workforce included approximately 164,000 employees.</p>
</body>
</html>
"""


@pytest.fixture
def mock_sec_service() -> SECService:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "company_tickers.json" in url:
            return httpx.Response(200, json=MOCK_TICKERS_JSON)
        if "CIK0000320193.json" in url:
            return httpx.Response(200, json=MOCK_AAPL_SUBMISSIONS)
        return httpx.Response(404)

    return SECService(client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture
def mock_document_service() -> DocumentService:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=MOCK_10K_HTML)

    return DocumentService(client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture
def mock_claims_service(mock_sec_service: SECService, mock_document_service: DocumentService) -> ClaimsService:
    return ClaimsService(sec_service=mock_sec_service, doc_service=mock_document_service)


@pytest.fixture
def client(
    mock_sec_service: SECService,
    mock_document_service: DocumentService,
    mock_claims_service: ClaimsService,
):
    app.dependency_overrides[get_sec_service] = lambda: mock_sec_service
    app.dependency_overrides[get_document_service] = lambda: mock_document_service
    app.dependency_overrides[get_claims_service] = lambda: mock_claims_service
    yield TestClient(app)
    app.dependency_overrides.clear()


# 1. Claims List Endpoint
def test_get_claims_endpoint_success(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/claims")
    assert response.status_code == 200
    data = response.json()

    assert data["company"]["ticker"] == "AAPL"
    assert data["filing"]["form_type"] == "10-K"
    assert data["total_claims"] >= 3
    assert len(data["claims"]) >= 3
    assert data["extraction_metadata"]["extraction_method"] == "deterministic"

    # Verify claim types in response
    claim_types = {c["claim_type"] for c in data["claims"]}
    assert "target" in claim_types or "current_state" in claim_types


def test_get_claims_endpoint_filter_by_type(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/claims?claim_type=target")
    assert response.status_code == 200
    data = response.json()

    for c in data["claims"]:
        assert c["claim_type"] == "target"


def test_get_claims_endpoint_filter_by_category(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/claims?category=environmental")
    assert response.status_code == 200
    data = response.json()

    for c in data["claims"]:
        assert c["category_group"] == "environmental"


# 2. Claim Summary Endpoint
def test_get_claim_summary_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/claims/summary")
    assert response.status_code == 200
    data = response.json()

    assert data["company"]["ticker"] == "AAPL"
    assert data["total_claims"] >= 3
    assert data["environmental_claims"] >= 1
    assert "by_category" in data
    assert "by_claim_type" in data


# 3. Individual Claim Endpoint
def test_get_individual_claim_endpoint_success(client: TestClient) -> None:
    # First get list of claims
    list_resp = client.get("/api/v1/companies/AAPL/claims")
    claims = list_resp.json()["claims"]
    assert len(claims) > 0
    target_claim = claims[0]

    # Fetch individual claim by ID
    claim_id = target_claim["claim_id"]
    response = client.get(f"/api/v1/companies/AAPL/claims/{claim_id}")
    assert response.status_code == 200
    data = response.json()

    assert data["claim_id"] == claim_id
    assert data["claim_text"] == target_claim["claim_text"]
    assert data["section_id"] == target_claim["section_id"]
    assert data["source_url"] == target_claim["source_url"]


def test_get_individual_claim_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/claims/claim_aapl_nonexistent_123456")
    assert response.status_code == 404
    assert response.json()["error"] == "claim_not_found"


# 4. Input Validation
def test_get_claims_invalid_ticker(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL$$$/claims")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_ticker"
