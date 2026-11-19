"""Unit tests for DocumentService covering retrieval, parsing, section detection, and passage extraction."""

import httpx
import pytest

from app.models.document import Document
from app.models.filing import SECFiling
from app.services.document_service import DocumentService
from app.utils.config import Settings
from app.utils.exceptions import (
    DocumentParsingError,
    DocumentRetrievalError,
    SECConnectionError,
    SECRateLimitError,
)

SAMPLE_10K_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>SAMPLE CORP - FORM 10-K ANNUAL REPORT</title>
    <style>body { font-family: Arial; }</style>
    <script>function doNothing() {}</script>
</head>
<body>
    <header><nav>Home &gt; Filings</nav></header>

    <div>Table of Contents</div>
    <div>Item 1. Business ......................... 1</div>
    <div>Item 1A. Risk Factors .................... 5</div>
    <div>Item 7. Management's Discussion ......... 10</div>
    <div>Item 8. Financial Statements ............. 20</div>

    <hr/>

    <h1>ITEM 1. BUSINESS</h1>
    <p>Sample Corp is committed to environmental sustainability and reducing carbon emissions across global supply chains.
    Our operations utilize 100% renewable energy in all corporate data centers. Net sales reached $12.4 billion, representing a 25.5% increase.</p>

    <h1>ITEM 1A. RISK FACTORS</h1>
    <p>Risks related to climate change and extreme weather events could adversely impact manufacturing facilities.
    We are subject to strict environmental regulations regarding waste and greenhouse gas emissions.</p>

    <h1>ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS</h1>
    <p>During fiscal year 2024, our workforce grew to 15,000 employees. We continue to invest in diversity and inclusion programs.
    Total capital expenditures included $250 million for energy efficiency initiatives.</p>

    <table>
        <tr><th>Metric</th><th>2024</th><th>2023</th></tr>
        <tr><td>Net Sales</td><td>$12.4 billion</td><td>$9.8 billion</td></tr>
        <tr><td>Renewable Energy %</td><td>85%</td><td>70%</td></tr>
    </table>

    <h1>ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA</h1>
    <p>Consolidated balance sheets and notes to financial statements for the period ended September 30, 2024.</p>
</body>
</html>
"""

MOCK_FILING = SECFiling(
    form_type="10-K",
    filing_date="2024-11-01",
    report_date="2024-09-30",
    accession_number="0001234567-24-000001",
    primary_document="sample-20240930.htm",
    filing_url="https://www.sec.gov/Archives/edgar/data/1234567/000123456724000001/sample-20240930.htm",
    fiscal_year=2024,
    is_amendment=False,
)


def create_mock_transport(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# 1. Retrieval Tests
def test_retrieve_raw_document_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SAMPLE_10K_HTML)

    service = DocumentService(client=create_mock_transport(handler))
    html = service.retrieve_raw_document("https://example.com/filing.htm")
    assert "SAMPLE CORP" in html
    assert "ITEM 1. BUSINESS" in html


def test_retrieve_raw_document_404_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    service = DocumentService(client=create_mock_transport(handler))
    with pytest.raises(DocumentRetrievalError, match="not found"):
        service.retrieve_raw_document("https://example.com/missing.htm")


def test_retrieve_raw_document_429_rate_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    service = DocumentService(client=create_mock_transport(handler))
    with pytest.raises(SECRateLimitError, match="rate limit exceeded"):
        service.retrieve_raw_document("https://example.com/filing.htm")


def test_retrieve_raw_document_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout reading document")

    service = DocumentService(client=create_mock_transport(handler))
    with pytest.raises(SECConnectionError, match="timeout"):
        service.retrieve_raw_document("https://example.com/filing.htm")


def test_retrieve_raw_document_http_500() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    service = DocumentService(client=create_mock_transport(handler))
    with pytest.raises(DocumentRetrievalError, match="HTTP 500"):
        service.retrieve_raw_document("https://example.com/filing.htm")


# 2. HTML Parsing and Cleaning Tests
def test_clean_and_normalize_html_removes_scripts_and_styles() -> None:
    service = DocumentService()
    cleaned_text, title = service.clean_and_normalize_html(SAMPLE_10K_HTML)

    assert title == "SAMPLE CORP - FORM 10-K ANNUAL REPORT"
    assert "doNothing" not in cleaned_text
    assert "font-family" not in cleaned_text
    assert "Home &gt; Filings" not in cleaned_text


def test_clean_and_normalize_html_preserves_numbers_and_financials() -> None:
    service = DocumentService()
    cleaned_text, _ = service.clean_and_normalize_html(SAMPLE_10K_HTML)

    # Verifies numbers, dollar amounts, and percentages are NOT corrupted
    assert "$12.4 billion" in cleaned_text
    assert "25.5%" in cleaned_text
    assert "$250 million" in cleaned_text
    assert "15,000 employees" in cleaned_text
    assert "85%" in cleaned_text


def test_clean_and_normalize_html_preserves_table_structure() -> None:
    service = DocumentService()
    cleaned_text, _ = service.clean_and_normalize_html(SAMPLE_10K_HTML)

    # Tables are formatted with pipe delimiters
    assert "Metric | 2024 | 2023" in cleaned_text
    assert "Net Sales | $12.4 billion | $9.8 billion" in cleaned_text


def test_clean_and_normalize_html_empty_error() -> None:
    service = DocumentService()
    with pytest.raises(DocumentParsingError, match="empty"):
        service.clean_and_normalize_html("")


# 3. Section Extraction Tests
def test_detect_sections_standard_10k_items() -> None:
    service = DocumentService()
    cleaned_text, _ = service.clean_and_normalize_html(SAMPLE_10K_HTML)
    sections = service.detect_sections(cleaned_text)

    section_ids = [s.section_id for s in sections]
    assert "item_1" in section_ids
    assert "item_1a" in section_ids
    assert "item_7" in section_ids
    assert "item_8" in section_ids

    item_1 = next(s for s in sections if s.section_id == "item_1")
    assert item_1.section_type == "business"
    assert "renewable energy" in item_1.text
    assert "$12.4 billion" in item_1.text

    item_1a = next(s for s in sections if s.section_id == "item_1a")
    assert item_1a.section_type == "risk_factors"
    assert "climate change" in item_1a.text

    item_7 = next(s for s in sections if s.section_id == "item_7")
    assert item_7.section_type == "mda"
    assert "workforce" in item_7.text


def test_detect_sections_heading_variations() -> None:
    html_with_variations = """
    <div>
    Item 1: Business Overview
    This is the business section content with meaningful details about company products and markets.
    <br/><br/>
    ITEM 1A — RISK FACTORS
    Significant operational and regulatory risks exist.
    <br/><br/>
    Item 7. Management's Discussion and Analysis of Financial Condition
    Detailed financial operational performance discussions.
    </div>
    """
    service = DocumentService()
    cleaned, _ = service.clean_and_normalize_html(html_with_variations)
    sections = service.detect_sections(cleaned)

    assert len(sections) == 3
    assert sections[0].section_id == "item_1"
    assert sections[1].section_id == "item_1a"
    assert sections[2].section_id == "item_7"


def test_detect_sections_fallback_full_document() -> None:
    unstructured_text = "This document does not contain SEC item headings. It has general text and disclosures."
    service = DocumentService()
    sections = service.detect_sections(unstructured_text)

    assert len(sections) == 1
    assert sections[0].section_id == "full_document"
    assert sections[0].section_title == "Full Document"


# 4. Relevant Passage Extraction Tests
def test_find_relevant_passages_keyword_matching() -> None:
    service = DocumentService()
    doc = service.process_document(filing=MOCK_FILING, html_content=SAMPLE_10K_HTML)

    passages = service.find_relevant_passages(
        document=doc,
        company_ticker="SAMPLE",
        keywords=["renewable energy", "climate change", "diversity"],
    )

    assert len(passages) >= 2
    matched_kws = {kw for p in passages for kw in p.matched_keywords}
    assert "renewable energy" in matched_kws or "climate change" in matched_kws

    # Check traceability fields
    for p in passages:
        assert p.company_ticker == "SAMPLE"
        assert p.accession_number == MOCK_FILING.accession_number
        assert p.source_url == MOCK_FILING.filing_url
        assert p.section_id != ""
        assert p.text != ""


def test_find_relevant_passages_no_match() -> None:
    service = DocumentService()
    doc = service.process_document(filing=MOCK_FILING, html_content=SAMPLE_10K_HTML)

    passages = service.find_relevant_passages(
        document=doc,
        company_ticker="SAMPLE",
        keywords=["nonexistentkeyword12345"],
    )
    assert len(passages) == 0


def test_find_relevant_passages_max_limit() -> None:
    service = DocumentService()
    doc = service.process_document(filing=MOCK_FILING, html_content=SAMPLE_10K_HTML)

    passages = service.find_relevant_passages(
        document=doc,
        company_ticker="SAMPLE",
        keywords=["energy", "emissions", "climate", "workforce"],
        max_passages=1,
    )
    assert len(passages) == 1


# 5. In-Memory Caching Test
def test_document_service_in_memory_caching() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text=SAMPLE_10K_HTML)

    service = DocumentService(client=create_mock_transport(handler))
    doc1 = service.process_document(filing=MOCK_FILING)
    doc2 = service.process_document(filing=MOCK_FILING)

    # Second call should use cache, not hit the transport again
    assert doc1.accession_number == doc2.accession_number
    assert calls == 1

    # After clearing cache, transport is called again
    service.clear_cache()
    service.process_document(filing=MOCK_FILING)
    assert calls == 2
