"""API tests for SEC 10-K document inspection, sections, and relevant passages endpoints."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.company import Company
from app.models.filing import SECFiling
from app.services.document_service import DocumentService, get_document_service
from app.services.sec_service import SECService, get_sec_service

# Mock SEC Data
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
    <p>Apple designs, manufactures and markets smartphones, personal computers, and accessories.
    The Company is committed to carbon neutral supply chains and environmental sustainability.
    All corporate operations are powered by 100% renewable energy.</p>

    <h1>ITEM 1A. RISK FACTORS</h1>
    <p>Global climate risks and natural disasters can disrupt global logistics and component suppliers.
    Environmental compliance costs may increase in response to greenhouse gas regulations.</p>

    <h1>ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS</h1>
    <p>The Company workforce included approximately 164,000 full-time equivalent employees.
    Net sales were $391.0 billion in fiscal 2024.</p>
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
def client(mock_sec_service: SECService, mock_document_service: DocumentService):
    app.dependency_overrides[get_sec_service] = lambda: mock_sec_service
    app.dependency_overrides[get_document_service] = lambda: mock_document_service
    yield TestClient(app)
    app.dependency_overrides.clear()


# 1. Document Metadata Endpoint
def test_get_document_metadata_endpoint_success(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/filings/latest/document")
    assert response.status_code == 200
    data = response.json()

    assert data["company"]["ticker"] == "AAPL"
    assert data["accession_number"] == "0000320193-25-000079"
    assert data["form_type"] == "10-K"
    assert data["title"] == "Apple Inc. Form 10-K"
    assert data["word_count"] > 20
    assert data["character_count"] > 100
    assert data["total_sections"] == 3
    assert len(data["detected_sections"]) == 3


def test_get_document_metadata_endpoint_invalid_ticker(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL$$$/filings/latest/document")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_ticker"


# 2. Document Sections Endpoint
def test_get_document_sections_endpoint_success(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/filings/latest/document/sections")
    assert response.status_code == 200
    data = response.json()

    assert data["company"]["ticker"] == "AAPL"
    assert data["total_sections"] == 3
    assert len(data["sections"]) == 3

    section_ids = [s["section_id"] for s in data["sections"]]
    assert "item_1" in section_ids
    assert "item_1a" in section_ids
    assert "item_7" in section_ids


def test_get_document_sections_endpoint_filter_by_type(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/filings/latest/document/sections?section_type=business")
    assert response.status_code == 200
    data = response.json()

    assert data["total_sections"] == 1
    assert data["sections"][0]["section_id"] == "item_1"
    assert data["sections"][0]["section_type"] == "business"


# 3. Relevant Passages Endpoint
def test_get_relevant_passages_endpoint_default_esg_keywords(client: TestClient) -> None:
    response = client.get("/api/v1/companies/AAPL/filings/latest/document/relevant-passages")
    assert response.status_code == 200
    data = response.json()

    assert data["company"]["ticker"] == "AAPL"
    assert data["total_passages"] >= 2
    assert len(data["passages"]) >= 2

    # Check traceability on first passage
    first_passage = data["passages"][0]
    assert first_passage["company_ticker"] == "AAPL"
    assert first_passage["accession_number"] == "0000320193-25-000079"
    assert first_passage["section_id"] in ("item_1", "item_1a", "item_7")
    assert len(first_passage["matched_keywords"]) > 0


def test_get_relevant_passages_endpoint_custom_keywords(client: TestClient) -> None:
    response = client.get(
        "/api/v1/companies/AAPL/filings/latest/document/relevant-passages?keywords=renewable energy,workforce"
    )
    assert response.status_code == 200
    data = response.json()

    assert data["total_passages"] >= 2
    matched = {kw for p in data["passages"] for kw in p["matched_keywords"]}
    assert "renewable energy" in matched or "workforce" in matched


# 4. Error Handling
def test_get_document_retrieval_failure(client: TestClient) -> None:
    def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Filing not on SEC server")

    doc_service = DocumentService(client=httpx.Client(transport=httpx.MockTransport(error_handler)))
    app.dependency_overrides[get_document_service] = lambda: doc_service

    response = client.get("/api/v1/companies/AAPL/filings/latest/document")
    assert response.status_code == 502
    assert response.json()["error"] == "document_retrieval_error"
