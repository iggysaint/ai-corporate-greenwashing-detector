"""API integration tests for Phase 6 LLM & Consistency Evaluation endpoints."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.claims_service import ClaimsService, get_claims_service
from app.services.document_service import DocumentService, get_document_service
from app.services.evidence_service import EvidenceService, get_evidence_service
from app.services.llm_service import LLMService, get_llm_service
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
def mock_llm_service(
    mock_sec_service: SECService,
    mock_document_service: DocumentService,
    mock_claims_service: ClaimsService,
    mock_evidence_service: EvidenceService,
) -> LLMService:
    return LLMService(
        sec_service=mock_sec_service,
        doc_service=mock_document_service,
        claims_service=mock_claims_service,
        evidence_service=mock_evidence_service,
    )


@pytest.fixture
def client(
    mock_sec_service: SECService,
    mock_document_service: DocumentService,
    mock_claims_service: ClaimsService,
    mock_evidence_service: EvidenceService,
    mock_llm_service: LLMService,
):
    app.dependency_overrides[get_sec_service] = lambda: mock_sec_service
    app.dependency_overrides[get_document_service] = lambda: mock_document_service
    app.dependency_overrides[get_claims_service] = lambda: mock_claims_service
    app.dependency_overrides[get_evidence_service] = lambda: mock_evidence_service
    app.dependency_overrides[get_llm_service] = lambda: mock_llm_service
    yield TestClient(app)
    app.dependency_overrides.clear()


# 1. Company Evaluations Endpoint Success
def test_get_company_evaluations_endpoint_success(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/evaluations")
    assert response.status_code == 200
    data = response.json()

    assert data["company"]["ticker"] == "AAPL"
    assert data["company"]["company_name"] == "Apple Inc."
    assert data["filing_accession_number"] == "0000320193-25-000079"
    assert data["provider_mode"] == "rule_based"
    assert "summary" in data
    assert data["summary"]["total_claims_evaluated"] >= 2
    assert len(data["evaluations"]) >= 2

    first_eval = data["evaluations"][0]
    assert "evaluation_id" in first_eval
    assert "claim_id" in first_eval
    assert "assessment" in first_eval
    assert "confidence" in first_eval
    assert "reasoning" in first_eval
    assert "evaluation_mode" in first_eval
    assert first_eval["evaluation_mode"] == "rule_based"


# 2. Evaluation Summary Endpoint Success
def test_get_evaluation_summary_endpoint_success(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/evaluations/summary")
    assert response.status_code == 200
    data = response.json()

    assert "total_claims_evaluated" in data
    assert "supported_count" in data
    assert "partially_supported_count" in data
    assert "inconsistent_count" in data
    assert "unsubstantiated_count" in data
    assert "insufficient_evidence_count" in data
    assert "rule_based_evaluations_count" in data
    assert data["total_claims_evaluated"] >= 2


# 3. Filter by Assessment
def test_get_company_evaluations_filter_by_assessment(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/evaluations?assessment=supported")
    assert response.status_code == 200
    data = response.json()

    for ev in data["evaluations"]:
        assert ev["assessment"] == "supported"


# 4. Filter by Category and Limit
def test_get_company_evaluations_filter_by_category_and_limit(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/evaluations?category=renewable_energy&limit=1")
    assert response.status_code == 200
    data = response.json()

    assert len(data["evaluations"]) <= 1
    if data["evaluations"]:
        assert data["evaluations"][0]["category"] == "renewable_energy"


# 5. Single Claim Evaluation Endpoint
def test_get_single_claim_evaluation_endpoint(client: TestClient) -> None:
    # First get company evaluations to pick a valid claim ID
    all_resp = client.get("/api/v1/companies/AAPL/evaluations")
    assert all_resp.status_code == 200
    first_claim_id = all_resp.json()["evaluations"][0]["claim_id"]

    # Now request single claim evaluation
    resp = client.get(f"/api/v1/companies/AAPL/claims/{first_claim_id}/evaluation")
    assert resp.status_code == 200
    single_data = resp.json()

    assert single_data["evaluation"]["claim_id"] == first_claim_id
    assert "assessment" in single_data["evaluation"]
    assert "reasoning" in single_data["evaluation"]
    assert single_data["provider_mode"] == "rule_based"


# 6. Single Claim Evaluation Not Found
def test_get_single_claim_evaluation_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/claims/claim_non_existent_id/evaluation")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "claim_not_found"


# 7. Invalid Ticker Handling
def test_get_evaluations_invalid_ticker(client: TestClient) -> None:
    response = client.get("/api/v1/companies/INVALID_TICKER_123/evaluations")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_ticker"


# 8. Unknown Ticker Handling
def test_get_evaluations_unknown_ticker(client: TestClient) -> None:
    response = client.get("/api/v1/companies/ZZZZ/evaluations")
    assert response.status_code == 404
    assert response.json()["error"] == "company_not_found"
