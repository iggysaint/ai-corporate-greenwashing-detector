"""Tests for Ghana Stock Exchange (GSE) integration.

Covers:
- Market model validation
- GSE company discovery (mocked API responses)
- GSE ticker normalization
- Document retrieval (HTML and PDF, mocked)
- Document parsing failure handling
- Ghana-specific ESG keywords
- GSE API endpoints (via TestClient)
- Multi-market separation (SEC + GSE independent)
- Duplicate document caching
- Missing/inaccessible document handling
"""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.market import (
    DocumentSourceType,
    GSECompany,
    GSECompanyDetailResponse,
    GSECompanyListResponse,
    GSEDocumentResponse,
    MarketDocument,
    MarketIdentifier,
)
from app.services.gse_service import (
    GSECompanyNotFoundError,
    GSEConnectionError,
    GSEDocumentParsingError,
    GSEService,
    GSEServiceError,
    extract_text_from_html,
    normalize_gse_ticker,
)


client = TestClient(app)


# ─────────────────────────────────────────────────────────
# Mock Data
# ─────────────────────────────────────────────────────────

MOCK_GSE_EQUITIES_LIST = [
    ["MTN Ghana Ltd", "MTNGH", "Telecommunications"],
    ["Ghana Commercial Bank Ltd", "GCB", "Banking"],
    ["Goil PLC", "GOIL", "Oil Marketing"],
    ["AngloGold Ashanti Ltd", "AGA", "Mining"],
    ["Unilever Ghana PLC", "UNIL", "Consumer Goods"],
]

MOCK_GSE_EQUITIES_DICT_LIST = [
    {"name": "MTN Ghana Ltd", "symbol": "MTNGH", "sector": "Telecommunications"},
    {"name": "Ghana Commercial Bank Ltd", "symbol": "GCB", "sector": "Banking"},
    {"name": "Goil PLC", "symbol": "GOIL", "sector": "Oil Marketing"},
]

MOCK_GSE_SINGLE_EQUITY = {
    "name": "MTN Ghana Ltd",
    "symbol": "MTNGH",
    "sector": "Telecommunications",
    "shares_outstanding": 21534240000,
    "market_cap": 38760000000.0,
}

# Actual Kwayisi API listing format: {"name": "TICKER", "price": X}
MOCK_KWAYISI_LIVE_LISTING = [
    {"name": "MTNGH", "price": 6.61},
    {"name": "GCB", "price": 8.50},
    {"name": "GOIL", "price": 2.10},
]

# Actual Kwayisi API single equity format with nested company info
MOCK_KWAYISI_LIVE_DETAIL = {
    "name": "MTNGH",
    "company": {
        "name": "Scancom Plc",
        "sector": "Telecommunications",
        "industry": "Mobile Telecommunications",
        "address": "MTN House, Independence Avenue, West Ridge, Accra, Ghana",
        "website": "mtn.com.gh",
    },
    "shares": 13236175050,
    "capital": 87491117080.5,
    "price": 6.61,
}

MOCK_SUSTAINABILITY_HTML = """
<html>
<head><title>MTN Ghana Sustainability Report 2024</title></head>
<body>
<h1>MTN Ghana Sustainability Report 2024</h1>
<p>MTN Ghana is committed to sustainable business practices across all operations.
The company has implemented a comprehensive environmental management system to reduce
its carbon footprint and minimize the environmental impact of its telecommunications
infrastructure.</p>

<h2>Environmental Stewardship</h2>
<p>In 2024, MTN Ghana reduced its Scope 1 emissions by 15% compared to the 2022 baseline.
The company transitioned 200 base stations to solar hybrid power systems, reducing diesel
consumption by 1.2 million liters. Water stewardship remains a priority, with 100% of
facilities implementing water recycling programs.</p>

<h2>Social Impact</h2>
<p>The MTN Ghana Foundation invested GHS 25 million in community development projects,
focusing on education, health, and economic empowerment. The company maintains a strict
equal opportunity employment policy and achieved 38% female representation in management
positions. Worker safety programs reduced lost-time injuries by 22% year-over-year.</p>

<h2>Governance</h2>
<p>MTN Ghana adheres to the SEC Ghana Corporate Governance Code and the GSE Sustainability
Disclosure Guidance. The Board of Directors includes three independent non-executive
directors. Anti-corruption training was completed by 100% of employees.</p>

<h2>Supply Chain</h2>
<p>All tier-1 suppliers are required to comply with MTN's Supplier Code of Conduct,
which includes provisions for environmental protection, labor rights, and anti-corruption.
In 2024, 95% of suppliers completed the annual sustainability assessment.</p>
</body>
</html>
"""

MOCK_ANNUAL_REPORT_TEXT = """
ANNUAL REPORT 2024

Ghana Commercial Bank Limited
Financial Statements for the Year Ended December 31, 2024

The Bank is committed to financial inclusion across Ghana, providing banking
services to underserved communities through our network of 190 branches and
1,500 mobile money agents.

Environmental responsibility: GCB has implemented a paperless banking initiative
reducing paper consumption by 40% since 2022. Energy-efficient LED lighting has
been installed in all branches, reducing electricity consumption by 18%.

Community development: The GCB Foundation invested GHS 5 million in educational
scholarships and healthcare infrastructure in rural communities.

Corporate Governance: The Bank complies with the Bank of Ghana Corporate Governance
Directive 2018 and the SEC Ghana Code of Best Practices.
"""


# ─────────────────────────────────────────────────────────
# Model Validation Tests
# ─────────────────────────────────────────────────────────

def test_gse_company_model_valid():
    """Verify GSECompany Pydantic model accepts valid data."""
    company = GSECompany(
        ticker="MTNGH",
        company_name="MTN Ghana Ltd",
        sector="Telecommunications",
        currency="GHS",
    )
    assert company.ticker == "MTNGH"
    assert company.market == MarketIdentifier.GH_GSE
    assert company.currency == "GHS"


def test_market_document_model_valid():
    """Verify MarketDocument Pydantic model accepts valid data."""
    doc = MarketDocument(
        document_id="doc_gse_abc123",
        company_ticker="MTNGH",
        company_name="MTN Ghana Ltd",
        market=MarketIdentifier.GH_GSE,
        source_type=DocumentSourceType.ANNUAL_REPORT,
        title="MTN Ghana Annual Report 2024",
        retrieval_status="retrieved",
        text_content="Sample text content here.",
        text_length=25,
        word_count=4,
        format="html",
    )
    assert doc.market == MarketIdentifier.GH_GSE
    assert doc.source_type == DocumentSourceType.ANNUAL_REPORT
    assert doc.retrieval_status == "retrieved"


def test_market_identifier_enum():
    """Verify MarketIdentifier enum has expected values."""
    assert MarketIdentifier.US_SEC.value == "us_sec"
    assert MarketIdentifier.GH_GSE.value == "gh_gse"


def test_document_source_type_enum():
    """Verify DocumentSourceType enum covers expected document types."""
    assert DocumentSourceType.SEC_10K.value == "sec_10k"
    assert DocumentSourceType.ANNUAL_REPORT.value == "annual_report"
    assert DocumentSourceType.SUSTAINABILITY_REPORT.value == "sustainability_report"
    assert DocumentSourceType.INTEGRATED_REPORT.value == "integrated_report"


# ─────────────────────────────────────────────────────────
# Ticker Normalization Tests
# ─────────────────────────────────────────────────────────

def test_normalize_gse_ticker_valid():
    """Valid GSE tickers are uppercased."""
    assert normalize_gse_ticker("mtngh") == "MTNGH"
    assert normalize_gse_ticker("GCB") == "GCB"
    assert normalize_gse_ticker("  goil  ") == "GOIL"


def test_normalize_gse_ticker_empty():
    """Empty ticker raises GSEServiceError."""
    with pytest.raises(GSEServiceError, match="cannot be empty"):
        normalize_gse_ticker("")


def test_normalize_gse_ticker_invalid_format():
    """Invalid ticker format raises GSEServiceError."""
    with pytest.raises(GSEServiceError, match="Invalid GSE ticker format"):
        normalize_gse_ticker("MTN-GH!")


# ─────────────────────────────────────────────────────────
# GSE Service — Company Discovery (Mocked)
# ─────────────────────────────────────────────────────────

def _mock_gse_service_with_list(equities_data) -> GSEService:
    """Create a GSEService with a mocked HTTP client returning equities data."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = equities_data
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = mock_response

    return GSEService(http_client=mock_client)


def test_get_listed_companies_array_format():
    """GSEService parses array-format equities response (Kwayisi API)."""
    service = _mock_gse_service_with_list(MOCK_GSE_EQUITIES_LIST)
    result = service.get_listed_companies()

    assert isinstance(result, GSECompanyListResponse)
    assert result.total_count == 5
    assert result.market == MarketIdentifier.GH_GSE
    assert result.companies[0].ticker == "MTNGH"
    assert result.companies[0].company_name == "MTN Ghana Ltd"
    assert result.companies[0].sector == "Telecommunications"


def test_get_listed_companies_dict_format():
    """GSEService parses object-format equities response."""
    service = _mock_gse_service_with_list(MOCK_GSE_EQUITIES_DICT_LIST)
    result = service.get_listed_companies()

    assert result.total_count == 3
    assert result.companies[0].ticker == "MTNGH"
    assert result.companies[1].ticker == "GCB"


def test_get_listed_companies_kwayisi_live_format():
    """GSEService parses the actual Kwayisi live API format: {"name": "TICKER", "price": X}."""
    service = _mock_gse_service_with_list(MOCK_KWAYISI_LIVE_LISTING)
    result = service.get_listed_companies()

    assert result.total_count == 3
    assert result.companies[0].ticker == "MTNGH"
    assert result.companies[1].ticker == "GCB"
    assert result.companies[2].ticker == "GOIL"


def test_get_company_by_ticker_kwayisi_nested_company():
    """GSEService correctly parses the nested company object from Kwayisi detail endpoint."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_KWAYISI_LIVE_DETAIL
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = mock_response

    service = GSEService(http_client=mock_client)
    company = service.get_company_by_ticker("MTNGH")

    assert company.ticker == "MTNGH"
    assert company.company_name == "Scancom Plc"
    assert company.sector == "Telecommunications"
    assert company.shares_outstanding == 13236175050
    assert company.market_cap == 87491117080.5
    assert company.website == "mtn.com.gh"


def test_get_listed_companies_caching():
    """Second call to get_listed_companies returns cached results."""
    service = _mock_gse_service_with_list(MOCK_GSE_EQUITIES_LIST)

    result1 = service.get_listed_companies()
    result2 = service.get_listed_companies()

    assert result1.total_count == result2.total_count
    # HTTP client.get should only be called once (cached)
    assert service._client.get.call_count == 1


def test_get_company_by_ticker_from_cache():
    """After listing, get_company_by_ticker returns from cache."""
    service = _mock_gse_service_with_list(MOCK_GSE_EQUITIES_LIST)
    service.get_listed_companies()

    company = service.get_company_by_ticker("MTNGH")
    assert company.ticker == "MTNGH"
    assert company.company_name == "MTN Ghana Ltd"


def test_get_company_by_ticker_specific_endpoint():
    """GSEService uses specific equity endpoint for ticker lookup."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_GSE_SINGLE_EQUITY
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = mock_response

    service = GSEService(http_client=mock_client)
    company = service.get_company_by_ticker("MTNGH")

    assert company.ticker == "MTNGH"
    assert company.company_name == "MTN Ghana Ltd"
    assert company.sector == "Telecommunications"


def test_get_company_by_ticker_not_found():
    """GSEService raises GSECompanyNotFoundError for unknown ticker."""
    # Mock: specific endpoint returns 404, listing returns empty
    mock_response_404 = MagicMock()
    mock_response_404.status_code = 404
    mock_response_404.json.return_value = {}
    mock_response_404.raise_for_status = MagicMock()

    mock_response_empty = MagicMock()
    mock_response_empty.status_code = 200
    mock_response_empty.json.return_value = []
    mock_response_empty.raise_for_status = MagicMock()

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = [mock_response_404, mock_response_empty]

    service = GSEService(http_client=mock_client)

    with pytest.raises(GSECompanyNotFoundError, match="UNKNOWN"):
        service.get_company_by_ticker("UNKNOWN")


def test_get_listed_companies_connection_error():
    """GSEService raises GSEConnectionError on network failure."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = httpx.ConnectError("Connection refused")

    service = GSEService(http_client=mock_client)

    with pytest.raises(GSEConnectionError, match="Unable to connect"):
        service.get_listed_companies()


def test_get_listed_companies_malformed_response():
    """GSEService handles malformed entries gracefully."""
    malformed_data = [
        ["MTN Ghana Ltd", "MTNGH"],  # Valid 2-element array
        ["Incomplete"],  # Too short — should be skipped
        {"name": "GCB Ltd", "symbol": "GCB"},  # Valid dict
        None,  # Invalid — should be skipped
    ]
    service = _mock_gse_service_with_list(malformed_data)
    result = service.get_listed_companies()

    assert result.total_count == 2
    assert result.companies[0].ticker == "MTNGH"
    assert result.companies[1].ticker == "GCB"


# ─────────────────────────────────────────────────────────
# GSE Service — Document Discovery
# ─────────────────────────────────────────────────────────

def test_discover_company_documents():
    """discover_company_documents returns curated public reports for MTNGH and standard stubs for other issuers."""
    service = _mock_gse_service_with_list(MOCK_GSE_EQUITIES_LIST)
    service.get_listed_companies()

    # Curated issuer: MTNGH
    result_mtn = service.discover_company_documents("MTNGH")
    assert isinstance(result_mtn, GSECompanyDetailResponse)
    assert result_mtn.company.ticker == "MTNGH"
    assert len(result_mtn.documents) == 3
    assert all(d.company_ticker == "MTNGH" for d in result_mtn.documents)
    assert any("2024" in d.title for d in result_mtn.documents)
    assert all(d.source_url is not None for d in result_mtn.documents)

    # Standard uncurated issuer: GCB
    result_gcb = service.discover_company_documents("GCB")
    assert isinstance(result_gcb, GSECompanyDetailResponse)
    assert result_gcb.company.ticker == "GCB"
    assert len(result_gcb.documents) == 2
    assert result_gcb.documents[0].source_type == DocumentSourceType.ANNUAL_REPORT
    assert result_gcb.documents[1].source_type == DocumentSourceType.SUSTAINABILITY_REPORT
    assert all(d.retrieval_status == "pending" for d in result_gcb.documents)


# ─────────────────────────────────────────────────────────
# GSE Service — Document Retrieval (Mocked)
# ─────────────────────────────────────────────────────────

def _mock_gse_service_with_document(equities_data, doc_content, content_type="text/html"):
    """Create a GSEService with mocked company listing and document retrieval."""
    mock_listing_response = MagicMock()
    mock_listing_response.status_code = 200
    mock_listing_response.json.return_value = equities_data
    mock_listing_response.raise_for_status = MagicMock()

    mock_doc_response = MagicMock()
    mock_doc_response.status_code = 200
    mock_doc_response.text = doc_content
    mock_doc_response.content = doc_content.encode("utf-8") if isinstance(doc_content, str) else doc_content
    mock_doc_response.headers = {"content-type": content_type}
    mock_doc_response.raise_for_status = MagicMock()

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = [mock_listing_response, mock_doc_response]

    return GSEService(http_client=mock_client)


def test_retrieve_html_document():
    """GSEService retrieves and extracts text from HTML document."""
    service = _mock_gse_service_with_document(
        MOCK_GSE_EQUITIES_LIST,
        MOCK_SUSTAINABILITY_HTML,
        "text/html",
    )
    service.get_listed_companies()

    doc = service.retrieve_document_from_url(
        ticker="MTNGH",
        source_url="https://example.com/mtn-sustainability-2024.html",
        source_type=DocumentSourceType.SUSTAINABILITY_REPORT,
        reporting_period="2024",
    )

    assert doc.retrieval_status == "retrieved"
    assert doc.format == "html"
    assert doc.text_content is not None
    assert doc.word_count is not None
    assert doc.word_count > 50
    assert "carbon footprint" in doc.text_content
    assert "environmental management" in doc.text_content


def test_retrieve_document_connection_failure():
    """Failed document retrieval returns document with 'failed' status."""
    mock_listing_response = MagicMock()
    mock_listing_response.status_code = 200
    mock_listing_response.json.return_value = MOCK_GSE_EQUITIES_LIST
    mock_listing_response.raise_for_status = MagicMock()

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = [
        mock_listing_response,
        httpx.ConnectError("Connection refused"),
    ]

    service = GSEService(http_client=mock_client)
    service.get_listed_companies()

    doc = service.retrieve_document_from_url(
        ticker="MTNGH",
        source_url="https://broken.example.com/report.html",
    )

    assert doc.retrieval_status == "failed"
    assert doc.error_message is not None
    assert "Connection failed" in doc.error_message


def test_retrieve_document_insufficient_text():
    """Document with too little extractable text returns 'failed' status."""
    tiny_html = "<html><body><p>Short.</p></body></html>"
    service = _mock_gse_service_with_document(
        MOCK_GSE_EQUITIES_LIST,
        tiny_html,
        "text/html",
    )
    service.get_listed_companies()

    doc = service.retrieve_document_from_url(
        ticker="MTNGH",
        source_url="https://example.com/tiny.html",
    )

    assert doc.retrieval_status == "failed"
    assert "insufficient extractable text" in doc.error_message.lower()


def test_retrieve_document_caching():
    """Same document ID is cached and returned on repeated calls."""
    service = _mock_gse_service_with_document(
        MOCK_GSE_EQUITIES_LIST,
        MOCK_SUSTAINABILITY_HTML,
        "text/html",
    )
    service.get_listed_companies()

    doc1 = service.retrieve_document_from_url(
        ticker="MTNGH",
        source_url="https://example.com/report.html",
        source_type=DocumentSourceType.SUSTAINABILITY_REPORT,
        reporting_period="2024",
    )

    # Second call should use cache (only 2 mock responses configured)
    doc2 = service.retrieve_document_from_url(
        ticker="MTNGH",
        source_url="https://example.com/report.html",
        source_type=DocumentSourceType.SUSTAINABILITY_REPORT,
        reporting_period="2024",
    )

    assert doc1.document_id == doc2.document_id
    assert doc1.retrieval_status == "retrieved"


def test_retrieve_document_timeout():
    """Timeout during document download returns 'failed' status."""
    mock_listing_response = MagicMock()
    mock_listing_response.status_code = 200
    mock_listing_response.json.return_value = MOCK_GSE_EQUITIES_LIST
    mock_listing_response.raise_for_status = MagicMock()

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = [
        mock_listing_response,
        httpx.TimeoutException("Read timed out"),
    ]

    service = GSEService(http_client=mock_client)
    service.get_listed_companies()

    doc = service.retrieve_document_from_url(
        ticker="MTNGH",
        source_url="https://example.com/slow.pdf",
    )

    assert doc.retrieval_status == "failed"
    assert "timed out" in doc.error_message.lower()


# ─────────────────────────────────────────────────────────
# HTML Text Extraction
# ─────────────────────────────────────────────────────────

def test_extract_text_from_html_basic():
    """HTML extraction returns clean text."""
    html = "<html><body><h1>Title</h1><p>Body text here.</p><script>alert('x')</script></body></html>"
    text = extract_text_from_html(html)
    assert "Title" in text
    assert "Body text here" in text
    assert "alert" not in text


def test_extract_text_from_html_sustainability_report():
    """Full sustainability report HTML extracts all sections."""
    text = extract_text_from_html(MOCK_SUSTAINABILITY_HTML)
    assert "Environmental Stewardship" in text
    assert "Social Impact" in text
    assert "Governance" in text
    assert "carbon footprint" in text
    assert "GHS 25 million" in text


# ─────────────────────────────────────────────────────────
# Ghana-Specific ESG Keywords
# ─────────────────────────────────────────────────────────

def test_ghana_esg_keywords_base():
    """Base Ghana ESG keywords include galamsey and financial inclusion."""
    keywords = GSEService.get_ghana_esg_keywords()
    assert "galamsey" in keywords
    assert "financial inclusion" in keywords
    assert "water stewardship" in keywords
    assert "corporate governance code" in keywords


def test_ghana_esg_keywords_mining_sector():
    """Mining sector adds mining-specific keywords."""
    keywords = GSEService.get_ghana_esg_keywords(sector="Mining")
    assert "galamsey" in keywords
    assert "tailings" in keywords
    assert "artisanal mining" in keywords
    assert "mineral rights" in keywords


def test_ghana_esg_keywords_banking_sector():
    """Banking sector adds financial inclusion keywords."""
    keywords = GSEService.get_ghana_esg_keywords(sector="Banking")
    assert "financial inclusion" in keywords
    assert "mobile money" in keywords
    assert "microfinance" in keywords


def test_ghana_esg_keywords_deduplication():
    """Keywords are deduplicated."""
    keywords = GSEService.get_ghana_esg_keywords(sector="Mining")
    # "galamsey" appears in both base and mining sector — should appear only once
    assert keywords.count("galamsey") == 1


# ─────────────────────────────────────────────────────────
# Document ID Generation
# ─────────────────────────────────────────────────────────

def test_generate_document_id_deterministic():
    """Same inputs produce same document ID."""
    id1 = GSEService.generate_document_id("MTNGH", "annual_report", "2024")
    id2 = GSEService.generate_document_id("MTNGH", "annual_report", "2024")
    assert id1 == id2
    assert id1.startswith("doc_gse_")


def test_generate_document_id_differs_by_type():
    """Different source types produce different IDs."""
    id_annual = GSEService.generate_document_id("MTNGH", "annual_report", "2024")
    id_sustain = GSEService.generate_document_id("MTNGH", "sustainability_report", "2024")
    assert id_annual != id_sustain


def test_generate_document_id_differs_by_period():
    """Different reporting periods produce different IDs."""
    id_2023 = GSEService.generate_document_id("MTNGH", "annual_report", "2023")
    id_2024 = GSEService.generate_document_id("MTNGH", "annual_report", "2024")
    assert id_2023 != id_2024


# ─────────────────────────────────────────────────────────
# GSE API Endpoint Tests (via TestClient)
# ─────────────────────────────────────────────────────────

def test_gse_companies_endpoint():
    """GET /api/v1/gse/companies returns GSE companies (mocked)."""
    with patch("app.api.gse_routes.get_gse_service") as mock_get:
        mock_service = MagicMock(spec=GSEService)
        mock_service.get_listed_companies.return_value = GSECompanyListResponse(
            companies=[
                GSECompany(ticker="MTNGH", company_name="MTN Ghana Ltd"),
                GSECompany(ticker="GCB", company_name="Ghana Commercial Bank Ltd"),
            ],
            total_count=2,
        )
        mock_get.return_value = mock_service

        response = client.get("/api/v1/gse/companies")
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        assert data["companies"][0]["ticker"] == "MTNGH"


def test_gse_company_detail_endpoint():
    """GET /api/v1/gse/companies/{ticker} returns company detail (mocked)."""
    with patch("app.api.gse_routes.get_gse_service") as mock_get:
        mock_service = MagicMock(spec=GSEService)
        mock_service.discover_company_documents.return_value = GSECompanyDetailResponse(
            company=GSECompany(ticker="MTNGH", company_name="MTN Ghana Ltd"),
            documents=[
                MarketDocument(
                    document_id="doc_gse_abc123",
                    company_ticker="MTNGH",
                    company_name="MTN Ghana Ltd",
                    market=MarketIdentifier.GH_GSE,
                    source_type=DocumentSourceType.ANNUAL_REPORT,
                    title="MTN Ghana Annual Report",
                    retrieval_status="pending",
                    format="unknown",
                ),
            ],
        )
        mock_get.return_value = mock_service

        response = client.get("/api/v1/gse/companies/MTNGH")
        assert response.status_code == 200
        data = response.json()
        assert data["company"]["ticker"] == "MTNGH"
        assert len(data["documents"]) == 1


def test_gse_company_not_found_endpoint():
    """GET /api/v1/gse/companies/{ticker} returns 404 for unknown ticker."""
    with patch("app.api.gse_routes.get_gse_service") as mock_get:
        mock_service = MagicMock(spec=GSEService)
        mock_service.discover_company_documents.side_effect = GSECompanyNotFoundError(
            "Company with ticker 'FAKE' not found on the Ghana Stock Exchange"
        )
        mock_get.return_value = mock_service

        response = client.get("/api/v1/gse/companies/FAKE")
        assert response.status_code == 404
        assert "gse_company_not_found" in response.json()["error"]


def test_gse_esg_keywords_endpoint():
    """GET /api/v1/gse/esg-keywords returns Ghana ESG keywords."""
    response = client.get("/api/v1/gse/esg-keywords")
    assert response.status_code == 200
    keywords = response.json()
    assert isinstance(keywords, list)
    assert "galamsey" in keywords


def test_gse_esg_keywords_with_sector_endpoint():
    """GET /api/v1/gse/esg-keywords?sector=Mining returns sector-specific keywords."""
    response = client.get("/api/v1/gse/esg-keywords?sector=Mining")
    assert response.status_code == 200
    keywords = response.json()
    assert "mineral rights" in keywords


# ─────────────────────────────────────────────────────────
# Multi-Market Separation Tests
# ─────────────────────────────────────────────────────────

def test_gse_and_sec_services_independent():
    """GSEService and SECService are independent singletons."""
    from app.services.sec_service import SECService

    gse = GSEService()
    sec = SECService()

    # They should be different types — not the same service
    assert type(gse).__name__ == "GSEService"
    assert type(sec).__name__ == "SECService"

    # GSE service should not interfere with SEC caches
    gse._company_cache["MTNGH"] = GSECompany(ticker="MTNGH", company_name="MTN Ghana Ltd")
    assert not hasattr(sec, "_company_cache") or "MTNGH" not in getattr(sec, "_company_cache", {})


def test_market_identifier_distinguishes_sources():
    """MarketIdentifier correctly separates US/SEC from GH/GSE."""
    sec_market = MarketIdentifier.US_SEC
    gse_market = MarketIdentifier.GH_GSE

    assert sec_market != gse_market
    assert sec_market.value == "us_sec"
    assert gse_market.value == "gh_gse"


# ─────────────────────────────────────────────────────────
# Cache Clear Test
# ─────────────────────────────────────────────────────────

def test_clear_cache_clears_all():
    """clear_cache removes all cached data."""
    service = _mock_gse_service_with_list(MOCK_GSE_EQUITIES_LIST)
    service.get_listed_companies()
    assert len(service._company_cache) > 0
    assert service._listing_cache is not None

    service.clear_cache()
    assert len(service._company_cache) == 0
    assert service._listing_cache is None
    assert len(service._document_cache) == 0


# ─────────────────────────────────────────────────────────
# Format Detection Tests
# ─────────────────────────────────────────────────────────

def test_detect_format_pdf():
    """PDF detection from URL and Content-Type."""
    assert GSEService._detect_format("https://example.com/report.pdf", "") == "pdf"
    assert GSEService._detect_format("https://example.com/report", "application/pdf") == "pdf"


def test_detect_format_html():
    """HTML detection from URL and Content-Type."""
    assert GSEService._detect_format("https://example.com/page.html", "") == "html"
    assert GSEService._detect_format("https://example.com/page", "text/html; charset=utf-8") == "html"


def test_detect_format_unknown():
    """Unknown format when no indicators present."""
    assert GSEService._detect_format("https://example.com/data", "application/octet-stream") == "unknown"


# ─────────────────────────────────────────────────────────
# SEC Regression — Existing Tests Still Discoverable
# ─────────────────────────────────────────────────────────

def test_sec_pipeline_not_broken_by_gse_imports():
    """Importing GSE modules does not break existing SEC pipeline imports."""
    from app.services.sec_service import SECService, get_sec_service
    from app.services.document_service import DocumentService, get_document_service
    from app.services.claims_service import ClaimsService, get_claims_service
    from app.services.evidence_service import EvidenceService, get_evidence_service
    from app.services.llm_service import LLMService, get_llm_service
    from app.models import Company, SECFiling, Claim, Evidence, ClaimEvaluation

    # All imports should work without errors
    assert SECService is not None
    assert DocumentService is not None
    assert ClaimsService is not None
    assert EvidenceService is not None
    assert LLMService is not None


def test_health_endpoint_still_works():
    """Health endpoint still returns healthy after GSE integration."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


# ─────────────────────────────────────────────────────────
# Security & SSRF Protection Tests
# ─────────────────────────────────────────────────────────

from app.utils.exceptions import SecurityValidationError, SSRFSecurityError
from app.utils.security import is_ip_restricted, validate_external_url


def test_ssrf_rejects_loopback_and_private_ips():
    """validate_external_url rejects loopback and RFC 1918 private IP addresses."""
    with pytest.raises(SSRFSecurityError):
        validate_external_url("http://127.0.0.1/annual-report.pdf")

    with pytest.raises(SSRFSecurityError):
        validate_external_url("http://localhost/report.html")

    with pytest.raises(SSRFSecurityError):
        validate_external_url("http://10.0.0.1/doc.pdf")

    with pytest.raises(SSRFSecurityError):
        validate_external_url("http://192.168.1.50/report.pdf")

    with pytest.raises(SSRFSecurityError):
        validate_external_url("http://172.16.0.1/report.pdf")


def test_ssrf_rejects_cloud_metadata_service():
    """validate_external_url blocks AWS/GCP/Azure link-local metadata endpoints."""
    with pytest.raises(SSRFSecurityError):
        validate_external_url("http://169.254.169.254/latest/meta-data/")


def test_security_rejects_unsupported_schemes():
    """validate_external_url rejects non-HTTP(S) protocols."""
    with pytest.raises(SecurityValidationError) as exc:
        validate_external_url("ftp://ftp.example.com/report.pdf")
    assert "Unsupported URL scheme" in str(exc.value)

    with pytest.raises(SecurityValidationError) as exc:
        validate_external_url("file:///etc/passwd")
    assert "Unsupported URL scheme" in str(exc.value)


def test_security_rejects_blocked_file_extensions():
    """validate_external_url blocks executable and archive extensions."""
    for bad_url in [
        "https://example.com/malware.exe",
        "https://example.com/payload.sh",
        "https://example.com/archive.zip",
        "https://example.com/library.dll",
    ]:
        with pytest.raises(SecurityValidationError) as exc:
            validate_external_url(bad_url)
        assert "not permitted" in str(exc.value).lower()


def test_is_ip_restricted_comprehensive():
    """is_ip_restricted correctly flags private, loopback, and link-local ranges."""
    restricted, _ = is_ip_restricted("127.0.0.1")
    assert restricted is True

    restricted, _ = is_ip_restricted("::1")
    assert restricted is True

    restricted, _ = is_ip_restricted("10.10.10.10")
    assert restricted is True

    restricted, _ = is_ip_restricted("192.168.0.1")
    assert restricted is True

    restricted, _ = is_ip_restricted("169.254.1.1")
    assert restricted is True

    # Public IP: 8.8.8.8
    restricted, _ = is_ip_restricted("8.8.8.8")
    assert restricted is False


# ─────────────────────────────────────────────────────────
# GSE Analysis Pipeline Tests (Mocked)
# ─────────────────────────────────────────────────────────

def test_analyze_company_document_pipeline():
    """analyze_company_document runs claim extraction, evidence retrieval, and evaluation."""
    rich_sustainability_text = (
        "MTN Ghana (Scancom PLC) Annual Report 2024. "
        "We are committed to reducing our carbon emissions by 15.8% relative to our 2021 baseline. "
        "We achieved this reduction through solar solutions at our data centres. "
        "Scancom PLC achieved 50% female representation on our Board of Directors in 2024. "
        "The Board appointed Louisa Stephens as an INED in 2024, resulting in 50% female representation. "
        "Our environmental management system adheres strictly to EPA Ghana environmental regulations. "
    )
    service = _mock_gse_service_with_document(
        MOCK_GSE_EQUITIES_LIST,
        rich_sustainability_text,
        "text/html",
    )
    service.get_listed_companies()

    analysis = service.analyze_company_document(
        ticker="MTNGH",
        source_url="https://example.com/mtn-report-2024.html",
        reporting_period="2024",
    )

    assert analysis.company.ticker == "MTNGH"
    assert analysis.document.format == "html"
    assert analysis.total_claims_extracted > 0
    assert len(analysis.evaluations) == analysis.total_claims_extracted
    assert analysis.summary is not None
    assert analysis.summary.total_claims_evaluated == analysis.total_claims_extracted
    assert analysis.summary.supported_count >= 0


def test_gse_analyze_endpoint_success():
    """POST /api/v1/gse/companies/{ticker}/analyze runs analysis over valid document URL."""
    html_content = (
        "<html><body>"
        "<h1>Scancom PLC Sustainability Report 2024</h1>"
        "<p>We reduced carbon emissions by 15.8% relative to our 2021 baseline through solar power.</p>"
        "<p>We have achieved 50% female representation on our Board of Directors.</p>"
        "</body></html>"
    )
    with patch("app.services.gse_service.safe_download_document") as mock_safe_download:
        mock_safe_download.return_value = (html_content.encode("utf-8"), "text/html")
        response = client.post(
            "/api/v1/gse/companies/MTNGH/analyze",
            params={
                "source_url": "https://example.com/sustainability.html",
                "reporting_period": "2024",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["company"]["ticker"] == "MTNGH"
        assert data["document"]["format"] == "html"
        assert "summary" in data


def test_gse_analyze_endpoint_ssrf_rejection():
    """POST /api/v1/gse/companies/{ticker}/analyze rejects internal IP targets with 403."""
    response = client.post(
        "/api/v1/gse/companies/MTNGH/analyze",
        params={
            "source_url": "http://127.0.0.1/admin-secret.pdf",
        },
    )
    assert response.status_code == 403
    assert "prohibited" in response.json()["detail"].lower()


def test_gse_analyze_endpoint_blocked_extension():
    """POST /api/v1/gse/companies/{ticker}/analyze rejects executable files with 400."""
    response = client.post(
        "/api/v1/gse/companies/MTNGH/analyze",
        params={
            "source_url": "https://example.com/exploit.exe",
        },
    )
    assert response.status_code == 400
    assert "not permitted" in response.json()["detail"].lower()


def test_gse_invalid_ticker_returns_400():
    """Invalid GSE ticker symbols return 400 invalid_gse_ticker across detail and scoring endpoints."""
    for method, path in (
        ("GET", "/api/v1/gse/companies/MTN-GH!"),
        ("GET", "/api/v1/gse/companies/MTN-GH!/score"),
        ("GET", "/api/v1/gse/companies/MTN-GH!/score/breakdown"),
        ("GET", "/api/v1/gse/companies/MTN-GH!/score/history"),
        ("POST", "/api/v1/gse/companies/MTN-GH!/analyze"),
    ):
        response = client.request(method, path)
        assert response.status_code == 400, f"Expected 400 for {method} {path}, got {response.status_code}"
        body = response.json()
        assert body["error"] == "invalid_gse_ticker"
        assert "Invalid GSE ticker format" in body["detail"]


def test_gse_missing_source_url_for_uncurated_issuer_returns_422():
    """Requesting analysis or score for an uncurated GSE issuer without source_url returns 422."""
    from app.services.scoring_service import ScoringService, get_scoring_service

    gse_svc = _mock_gse_service_with_list(MOCK_GSE_EQUITIES_LIST)
    gse_svc.get_listed_companies()
    scoring_svc = ScoringService(gse_service=gse_svc)

    app.dependency_overrides[get_scoring_service] = lambda: scoring_svc
    try:
        with patch("app.api.gse_routes.get_gse_service", return_value=gse_svc):
            analyze_resp = client.post("/api/v1/gse/companies/GCB/analyze")
            assert analyze_resp.status_code == 422
            assert analyze_resp.json()["error"] == "gse_document_source_required"

            score_resp = client.get("/api/v1/gse/companies/GCB/score")
            assert score_resp.status_code == 422
            assert score_resp.json()["error"] == "gse_document_source_required"
    finally:
        app.dependency_overrides.pop(get_scoring_service, None)
