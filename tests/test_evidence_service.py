"""Unit tests for Evidence & Cross-Reference Engine (Phase 5).

Tests verify deterministic evidence retrieval, conservative relationship classification,
Item 1A risk disclosure rules, deduplication, source traceability, and absence of fabricated evidence.
"""

import pytest

from app.models.claim import Claim, ClaimCategoryGroup, ClaimType
from app.models.company import Company
from app.models.document import Document, DocumentSection
from app.models.evidence import (
    ClaimEvidenceResult,
    Evidence,
    EvidenceRelationship,
    EvidenceStrength,
    EvidenceType,
)
from app.models.filing import SECFiling
from app.services.claims_service import ClaimsService
from app.services.document_service import DocumentService
from app.services.evidence_service import EvidenceService
from app.services.sec_service import SECService

MOCK_COMPANY = Company(
    ticker="AAPL",
    company_name="Apple Inc.",
    cik="0000320193",
    exchange="Nasdaq",
    sic="3571",
    sic_description="Electronic Computers",
)

MOCK_FILING = SECFiling(
    form_type="10-K",
    filing_date="2025-10-31",
    report_date="2025-09-27",
    accession_number="0000320193-25-000079",
    primary_document="aapl-20250927.htm",
    filing_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
    fiscal_year=2025,
    is_amendment=False,
)


def create_mock_document(sections_text: list[tuple[str, str, str]]) -> Document:
    """Helper to create Document with specific sections [(id, title, text)]."""
    sections = []
    full_text_parts = []
    curr_pos = 0

    for sec_id, sec_title, sec_text in sections_text:
        start = curr_pos
        end = start + len(sec_text)
        sections.append(
            DocumentSection(
                section_id=sec_id,
                section_title=sec_title,
                section_type="business" if "1" in sec_id else ("risk_factors" if "1a" in sec_id else "mda"),
                text=sec_text,
                start_position=start,
                end_position=end,
                word_count=len(sec_text.split()),
            )
        )
        full_text_parts.append(sec_text)
        curr_pos = end + 2

    full_text = "\n\n".join(full_text_parts)
    return Document(
        accession_number=MOCK_FILING.accession_number,
        form_type=MOCK_FILING.form_type,
        filing_date=MOCK_FILING.filing_date,
        report_date=MOCK_FILING.report_date,
        source_url=MOCK_FILING.filing_url,
        title="Apple Inc. 2025 Form 10-K",
        text=full_text,
        word_count=len(full_text.split()),
        sections=sections,
    )


# 1. Model Validation
def test_evidence_model_validation() -> None:
    ev = Evidence(
        evidence_id="ev_test123",
        claim_id="cl_abc456",
        company_ticker="AAPL",
        company_name="Apple Inc.",
        evidence_text="We have transitioned 100% of our corporate operations to renewable electricity.",
        evidence_type=EvidenceType.QUANTITATIVE.value,
        relationship=EvidenceRelationship.SUPPORTING.value,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        report_date="2025-09-27",
        section_id="item_1",
        section_title="Item 1. Business",
        source_location="Item 1. Business",
        approximate_position=150,
        matched_concepts=["renewable energy", "100%"],
        matched_terms=["renewable", "energy", "100%"],
        relevance_score=0.85,
        evidence_strength=EvidenceStrength.STRONG.value,
        extraction_method="deterministic",
        confidence="high",
    )
    assert ev.evidence_id == "ev_test123"
    assert ev.relationship == "supporting"
    assert ev.relevance_score == 0.85
    assert ev.evidence_strength == "strong"
    assert ev.filing_accession_number == MOCK_FILING.accession_number


# 2. Evidence ID Stability
def test_evidence_id_deterministic() -> None:
    id1 = EvidenceService.generate_evidence_id(
        claim_id="cl_123",
        evidence_text="We achieved a 30% reduction in carbon emissions across corporate facilities.",
        section_id="item_7",
    )
    id2 = EvidenceService.generate_evidence_id(
        claim_id="cl_123",
        evidence_text="We achieved a 30% reduction in carbon emissions across corporate facilities.",
        section_id="item_7",
    )
    assert id1 == id2
    assert id1.startswith("ev_")


# 3. Supporting Evidence for Target Claim
def test_search_supporting_evidence_target_claim() -> None:
    service = EvidenceService()

    claim = Claim(
        claim_id="cl_target1",
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text="We aim to achieve net-zero carbon emissions across our entire supply chain by 2030.",
        claim_type=ClaimType.TARGET.value,
        category="carbon_neutrality",
        category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        section_id="item_1",
        section_title="Item 1. Business",
        source_excerpt="We aim to achieve net-zero carbon emissions across our entire supply chain by 2030.",
        source_location="Item 1. Business",
        target_year=2030,
        metric="carbon emissions",
        target_value="net zero",
        extraction_method="deterministic",
        confidence="high",
        status="active",
    )

    doc = create_mock_document([
        (
            "item_1",
            "Item 1. Business",
            "The Company has committed to a plan to achieve net-zero carbon emissions across all products by 2030.",
        ),
        (
            "item_8",
            "Item 8. Financial Statements",
            "Inventories are stated at the lower of cost or net realizable value using the first-in, first-out method.",
        ),
    ])

    evidence_list = service._search_evidence_for_claim(claim, doc, MOCK_FILING)
    assert len(evidence_list) >= 1
    top_ev = evidence_list[0]
    assert top_ev.relationship == EvidenceRelationship.SUPPORTING.value
    assert top_ev.relevance_score >= 0.30
    assert "2030" in top_ev.matched_terms or "carbon" in top_ev.matched_terms


# 4. Supporting Evidence for Achievement Claim
def test_search_supporting_evidence_achievement_claim() -> None:
    service = EvidenceService()

    claim = Claim(
        claim_id="cl_achieve1",
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text="We achieved a 30% reduction in greenhouse gas emissions across corporate operations.",
        claim_type=ClaimType.ACHIEVEMENT.value,
        category="greenhouse_gas",
        category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        section_id="item_7",
        section_title="Item 7. MD&A",
        source_excerpt="We achieved a 30% reduction in greenhouse gas emissions across corporate operations.",
        source_location="Item 7. MD&A",
        metric="greenhouse gas emissions",
        target_value="30%",
        unit="percent",
        extraction_method="deterministic",
        confidence="high",
        status="active",
    )

    doc = create_mock_document([
        (
            "item_7",
            "Item 7. MD&A",
            "During fiscal 2025, the Company achieved a 30% reduction in greenhouse gas emissions across corporate operations through energy efficiency measures.",
        ),
    ])

    evidence_list = service._search_evidence_for_claim(claim, doc, MOCK_FILING)
    assert len(evidence_list) == 1
    assert evidence_list[0].relationship == EvidenceRelationship.SUPPORTING.value
    assert evidence_list[0].evidence_strength in (EvidenceStrength.STRONG.value, EvidenceStrength.MODERATE.value)


# 5. Qualifying Evidence Detection
def test_search_qualifying_evidence() -> None:
    service = EvidenceService()

    claim = Claim(
        claim_id="cl_qual1",
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text="We target 100% renewable energy across all manufacturing operations by 2030.",
        claim_type=ClaimType.TARGET.value,
        category="renewable_energy",
        category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        section_id="item_1",
        section_title="Item 1. Business",
        source_excerpt="We target 100% renewable energy across all manufacturing operations by 2030.",
        source_location="Item 1. Business",
        target_year=2030,
        metric="renewable energy",
        target_value="100%",
        extraction_method="deterministic",
        confidence="high",
        status="active",
    )

    doc = create_mock_document([
        (
            "item_1",
            "Item 1. Business",
            "Our renewable energy initiatives are subject to regional grid availability and where feasible at selected facilities.",
        ),
    ])

    evidence_list = service._search_evidence_for_claim(claim, doc, MOCK_FILING)
    assert len(evidence_list) >= 1
    assert evidence_list[0].relationship == EvidenceRelationship.QUALIFYING.value


# 6. Item 1A Risk Factors Rule: Contextual Only
def test_item_1a_risk_factors_are_contextual_never_supporting() -> None:
    service = EvidenceService()

    claim = Claim(
        claim_id="cl_risk_check",
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text="We commit to 100% renewable electricity by 2030.",
        claim_type=ClaimType.TARGET.value,
        category="renewable_energy",
        category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        section_id="item_1",
        section_title="Item 1. Business",
        source_excerpt="We commit to 100% renewable electricity by 2030.",
        source_location="Item 1. Business",
        target_year=2030,
        metric="renewable electricity",
        target_value="100%",
        extraction_method="deterministic",
        confidence="high",
        status="active",
    )

    doc = create_mock_document([
        (
            "item_1a",
            "Item 1A. Risk Factors",
            "There can be no assurance that our initiatives to secure renewable electricity by 2030 will succeed, and failure to do so could adversely affect our brand.",
        ),
    ])

    evidence_list = service._search_evidence_for_claim(claim, doc, MOCK_FILING)
    assert len(evidence_list) >= 1
    # MUST NOT be supporting or contradictory
    assert evidence_list[0].relationship in (
        EvidenceRelationship.CONTEXTUAL.value,
        EvidenceRelationship.QUALIFYING.value,
    )
    assert evidence_list[0].relationship != EvidenceRelationship.SUPPORTING.value
    assert evidence_list[0].relationship != EvidenceRelationship.CONTRADICTORY.value


# 7. Contradictory Evidence Detection (Conservative)
def test_contradictory_evidence_detection() -> None:
    service = EvidenceService()

    claim = Claim(
        claim_id="cl_contra1",
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text="We achieved 100% renewable electricity across all operations.",
        claim_type=ClaimType.ACHIEVEMENT.value,
        category="renewable_energy",
        category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        section_id="item_7",
        section_title="Item 7. MD&A",
        source_excerpt="We achieved 100% renewable electricity across all operations.",
        source_location="Item 7. MD&A",
        metric="renewable electricity",
        target_value="100%",
        extraction_method="deterministic",
        confidence="high",
        status="active",
    )

    doc = create_mock_document([
        (
            "item_7",
            "Item 7. MD&A",
            "During fiscal 2025, the Company reached 45% renewable electricity across corporate operations, with fossil fuels comprising the remainder.",
        ),
    ])

    evidence_list = service._search_evidence_for_claim(claim, doc, MOCK_FILING)
    assert len(evidence_list) >= 1
    assert evidence_list[0].relationship == EvidenceRelationship.CONTRADICTORY.value


# 8. Different Reporting Years Not Flagged as Contradictory
def test_different_reporting_years_not_contradictory() -> None:
    service = EvidenceService()

    claim = Claim(
        claim_id="cl_year_guard",
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text="We achieved 80% renewable electricity in 2024.",
        claim_type=ClaimType.ACHIEVEMENT.value,
        category="renewable_energy",
        category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        section_id="item_7",
        section_title="Item 7. MD&A",
        source_excerpt="We achieved 80% renewable electricity in 2024.",
        source_location="Item 7. MD&A",
        target_year=2024,
        metric="renewable electricity",
        target_value="80%",
        extraction_method="deterministic",
        confidence="high",
        status="active",
    )

    doc = create_mock_document([
        (
            "item_7",
            "Item 7. MD&A",
            "In 2021, the Company reached 40% renewable electricity across corporate operations.",
        ),
    ])

    evidence_list = service._search_evidence_for_claim(claim, doc, MOCK_FILING)
    if evidence_list:
        # Differing years (2024 vs 2021) should NOT be flagged as contradictory
        assert evidence_list[0].relationship != EvidenceRelationship.CONTRADICTORY.value


# 9. Insufficient Evidence When No Meaningful Match
def test_insufficient_evidence_when_no_match() -> None:
    service = EvidenceService()

    claim = Claim(
        claim_id="cl_nomatch",
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text="We have committed to 100% zero-deforestation paper packaging by 2030.",
        claim_type=ClaimType.TARGET.value,
        category="biodiversity",
        category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        section_id="item_1",
        section_title="Item 1. Business",
        source_excerpt="We have committed to 100% zero-deforestation paper packaging by 2030.",
        source_location="Item 1. Business",
        target_year=2030,
        metric="zero-deforestation paper packaging",
        target_value="100%",
        extraction_method="deterministic",
        confidence="high",
        status="active",
    )

    doc = create_mock_document([
        (
            "item_8",
            "Item 8. Financial Statements",
            "Cash and cash equivalents consist of cash and short-term, highly liquid investments with maturities of three months or less.",
        ),
    ])

    evidence_list = service._search_evidence_for_claim(claim, doc, MOCK_FILING)
    assert len(evidence_list) == 0
    rel = service._determine_strongest_relationship(evidence_list)
    assert rel == EvidenceRelationship.INSUFFICIENT_EVIDENCE.value
    conf = service._overall_retrieval_confidence(evidence_list)
    assert conf == "insufficient"


# 10. Source Traceability Preserved
def test_source_traceability_preserved() -> None:
    service = EvidenceService()

    claim = Claim(
        claim_id="cl_trace1",
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text="We maintain a supplier code of conduct covering human rights and labor standards.",
        claim_type=ClaimType.POLICY.value,
        category="labor_practices",
        category_group=ClaimCategoryGroup.SOCIAL.value,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        section_id="item_1",
        section_title="Item 1. Business",
        source_excerpt="We maintain a supplier code of conduct covering human rights and labor standards.",
        source_location="Item 1. Business",
        extraction_method="deterministic",
        confidence="high",
        status="active",
    )

    doc = create_mock_document([
        (
            "item_1",
            "Item 1. Business",
            "The Company enforces a supplier code of conduct requiring compliance with international labor standards.",
        ),
    ])

    evidence_list = service._search_evidence_for_claim(claim, doc, MOCK_FILING)
    assert len(evidence_list) >= 1
    ev = evidence_list[0]

    assert ev.claim_id == claim.claim_id
    assert ev.company_ticker == "AAPL"
    assert ev.company_name == "Apple Inc."
    assert ev.filing_accession_number == MOCK_FILING.accession_number
    assert ev.source_url == MOCK_FILING.filing_url
    assert ev.section_id == "item_1"
    assert ev.section_title == "Item 1. Business"
    assert ev.approximate_position >= 0
    assert ev.extraction_method == "deterministic"


# 11. In-Memory Caching
def test_evidence_service_caching() -> None:
    service = EvidenceService()
    assert len(service._evidence_cache) == 0

    # Add mock result to cache
    mock_result = ClaimEvidenceResult(
        claim=Claim(
            claim_id="cl_cache",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            claim_text="We commit to 100% renewable electricity by 2030.",
            claim_type=ClaimType.TARGET.value,
            category="renewable_energy",
            category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
            source_type="sec_10k",
            source_title="Apple Inc. 2025 Form 10-K",
            source_url=MOCK_FILING.filing_url,
            filing_accession_number=MOCK_FILING.accession_number,
            filing_date="2025-10-31",
            section_id="item_1",
            section_title="Item 1. Business",
            source_excerpt="We commit to 100% renewable electricity by 2030.",
            source_location="Item 1. Business",
            target_year=2030,
            metric="renewable electricity",
            target_value="100%",
            extraction_method="deterministic",
            confidence="high",
            status="active",
        ),
        evidence=[],
        best_evidence=[],
        evidence_count=0,
        strongest_relationship="insufficient_evidence",
        overall_retrieval_confidence="insufficient",
    )
    service._evidence_cache[MOCK_FILING.accession_number] = [mock_result]
    assert MOCK_FILING.accession_number in service._evidence_cache

    service.clear_cache()
    assert len(service._evidence_cache) == 0


# 12. Quality Audit Test: Target Claim Not Satisfied by Achievement Language Alone
def test_target_claim_not_satisfied_by_unrelated_past_achievement() -> None:
    service = EvidenceService()

    claim = Claim(
        claim_id="cl_audit_target",
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text="We target reducing our carbon emissions by 50% across our supply chain by 2030.",
        claim_type=ClaimType.TARGET.value,
        category="greenhouse_gas",
        category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        section_id="item_1",
        section_title="Item 1. Business",
        source_excerpt="We target reducing our carbon emissions by 50% across our supply chain by 2030.",
        source_location="Item 1. Business",
        target_year=2030,
        metric="carbon emissions",
        target_value="50%",
        extraction_method="deterministic",
        confidence="high",
        status="active",
    )

    # Document mentions carbon emissions but only describes past operational work, not a commitment to the 2030 target
    doc = create_mock_document([
        (
            "item_7",
            "Item 7. MD&A",
            "In fiscal 2023, the Company reduced carbon emissions in corporate travel by 5% compared to fiscal 2022.",
        ),
    ])

    evidence_list = service._search_evidence_for_claim(claim, doc, MOCK_FILING)
    if evidence_list:
        # A past historical achievement disclosure must NOT be classified as supporting a future target commitment
        top_ev = evidence_list[0]
        assert top_ev.relationship != EvidenceRelationship.SUPPORTING.value
        assert top_ev.relationship == EvidenceRelationship.CONTEXTUAL.value


# 13. Quality Audit Test: Scope and Unit Differences Not Classified as Contradictions
def test_differing_scopes_and_units_not_contradictory() -> None:
    service = EvidenceService()

    claim = Claim(
        claim_id="cl_scope_guard",
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text="We achieved 100% renewable electricity in all data centers in 2025.",
        claim_type=ClaimType.ACHIEVEMENT.value,
        category="renewable_energy",
        category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        section_id="item_7",
        section_title="Item 7. MD&A",
        source_excerpt="We achieved 100% renewable electricity in all data centers in 2025.",
        source_location="Item 7. MD&A",
        target_year=2025,
        metric="renewable electricity data centers",
        target_value="100%",
        extraction_method="deterministic",
        confidence="high",
        status="active",
    )

    # Document reports 25% for a DIFFERENT scope (manufacturing facilities, not data centers)
    doc = create_mock_document([
        (
            "item_7",
            "Item 7. MD&A",
            "In 2025, the Company sourced 25% renewable electricity for contract manufacturing facilities.",
        ),
    ])

    evidence_list = service._search_evidence_for_claim(claim, doc, MOCK_FILING)
    if evidence_list:
        # Scope difference must NOT be classified as contradictory
        assert evidence_list[0].relationship != EvidenceRelationship.CONTRADICTORY.value


# 14. Quality Audit Test: Paragraph Segmentation on Single Newlines
def test_single_newline_paragraph_segmentation() -> None:
    service = EvidenceService()

    claim = Claim(
        claim_id="cl_single_nl",
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text="The Company is committed to inclusion and to providing an equal opportunity workplace.",
        claim_type=ClaimType.POLICY.value,
        category="inclusion",
        category_group=ClaimCategoryGroup.SOCIAL.value,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        section_id="item_1",
        section_title="Item 1. Business",
        source_excerpt="The Company is committed to inclusion and to providing an equal opportunity workplace.",
        source_location="Item 1. Business",
        extraction_method="deterministic",
        confidence="high",
        status="active",
    )

    # Section text formatted with single newlines between paragraphs (standard BeautifulSoup output)
    section_text = (
        "Item 1. Business\n"
        "Company Overview and product lines including phones and computers.\n"
        "The Company is committed to inclusion and to providing an equal opportunity workplace free of discrimination.\n"
        "Available Information and SEC filings access instructions."
    )

    doc = Document(
        document_id="doc_test_single_nl",
        company_ticker="AAPL",
        accession_number=MOCK_FILING.accession_number,
        form_type="10-K",
        filing_date="2025-10-31",
        report_date="2025-09-27",
        source_url=MOCK_FILING.filing_url,
        title="Apple Form 10-K",
        text=section_text,
        word_count=50,
        sections=[
            DocumentSection(
                section_id="item_1",
                section_title="Item 1. Business",
                section_type="business",
                text=section_text,
                start_position=0,
                end_position=len(section_text),
                word_count=50,
            )
        ],
    )

    evidence_list = service._search_evidence_for_claim(claim, doc, MOCK_FILING)
    assert len(evidence_list) >= 1
    top_ev = evidence_list[0]
    # The top evidence must be the inclusion paragraph, NOT the entire 4-line section
    assert "inclusion" in top_ev.evidence_text
    assert "Company Overview and product lines" not in top_ev.evidence_text

