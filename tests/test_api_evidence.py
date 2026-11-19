"""API integration tests for Evidence & Cross-Reference Engine endpoints (Phase 5)."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.claims_service import ClaimsService, get_claims_service
from app.services.document_service import DocumentService, get_document_service
from app.services.evidence_service import EvidenceService, get_evidence_service
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
def mock_evidence_service(
    mock_sec_service: SECService,
    mock_document_service: DocumentService,
    mock_claims_service: ClaimsService,
) -> EvidenceService:
    return EvidenceService(
        sec_service=mock_sec_service,
        doc_service=mock_document_service,
        claims_service=mock_claims_service,
    )


@pytest.fixture
def client(
    mock_sec_service: SECService,
    mock_document_service: DocumentService,
    mock_claims_service: ClaimsService,
    mock_evidence_service: EvidenceService,
):
    app.dependency_overrides[get_sec_service] = lambda: mock_sec_service
    app.dependency_overrides[get_document_service] = lambda: mock_document_service
    app.dependency_overrides[get_claims_service] = lambda: mock_claims_service
    app.dependency_overrides[get_evidence_service] = lambda: mock_evidence_service
    yield TestClient(app)
    app.dependency_overrides.clear()


# 1. Company Evidence List Endpoint
def test_get_company_evidence_endpoint_success(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/evidence")
    assert response.status_code == 200
    data = response.json()

    assert data["company"]["ticker"] == "AAPL"
    assert data["company"]["company_name"] == "Apple Inc."
    assert data["filing_accession_number"] == "0000320193-25-000079"
    assert data["extraction_method"] == "deterministic"
    assert data["total_claims"] >= 2
    assert len(data["results"]) >= 2

    # Check structure of first result
    first = data["results"][0]
    assert "claim" in first
    assert "evidence" in first
    assert "best_evidence" in first
    assert "strongest_relationship" in first
    assert "overall_retrieval_confidence" in first


# 2. Filter by Category
def test_get_company_evidence_filter_by_category(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/evidence?category=environmental")
    assert response.status_code == 200
    data = response.json()

    for item in data["results"]:
        assert (
            item["claim"]["category"] == "environmental"
            or item["claim"]["category_group"] == "environmental"
        )


# 3. Filter by Claim Type
def test_get_company_evidence_filter_by_claim_type(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/evidence?claim_type=target")
    assert response.status_code == 200
    data = response.json()

    for item in data["results"]:
        assert item["claim"]["claim_type"] == "target"


# 4. Filter by Relationship
def test_get_company_evidence_filter_by_relationship(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/evidence?relationship=supporting")
    assert response.status_code == 200
    data = response.json()

    for item in data["results"]:
        assert item["strongest_relationship"] == "supporting"


# 5. Filter by Minimum Relevance
def test_get_company_evidence_filter_by_minimum_relevance(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/evidence?minimum_relevance=0.20")
    assert response.status_code == 200
    data = response.json()

    for item in data["results"]:
        if item["best_evidence"]:
            assert item["best_evidence"][0]["relevance_score"] >= 0.20


# 6. Single Claim Evidence Endpoint Success
def test_get_single_claim_evidence_endpoint_success(client: TestClient) -> None:
    # First get claims to get a real claim_id
    claims_resp = client.get("/api/v1/companies/AAPL/claims")
    assert claims_resp.status_code == 200
    claim_id = claims_resp.json()["claims"][0]["claim_id"]

    ev_resp = client.get(f"/api/v1/companies/AAPL/claims/{claim_id}/evidence")
    assert ev_resp.status_code == 200
    data = ev_resp.json()

    assert data["claim"]["claim_id"] == claim_id
    assert "evidence" in data
    assert "strongest_relationship" in data


# 7. Single Claim Evidence Endpoint Not Found
def test_get_single_claim_evidence_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/claims/cl_nonexistent999/evidence")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "claim_not_found"


# 8. Evidence Summary Endpoint
def test_get_evidence_summary_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/evidence/summary")
    assert response.status_code == 200
    data = response.json()

    assert data["company"]["ticker"] == "AAPL"
    assert data["filing_accession_number"] == "0000320193-25-000079"
    assert data["total_claims_analyzed"] >= 2
    assert data["extraction_method"] == "deterministic"
    assert "supporting_evidence_count" in data
    assert "contradictory_evidence_count" in data
    assert "qualifying_evidence_count" in data
    assert "contextual_evidence_count" in data
    assert "claims_with_evidence" in data
    assert "claims_insufficient_evidence" in data


# 9. Invalid Ticker
def test_get_company_evidence_invalid_ticker(client: TestClient) -> None:
    response = client.get("/api/v1/companies/INVALID_TICKER_123/evidence")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_ticker"
