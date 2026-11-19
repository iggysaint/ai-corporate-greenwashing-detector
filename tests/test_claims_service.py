"""Unit tests for sustainability claim extraction, normalization, deduplication, and source traceability."""

import pytest

from app.models.claim import Claim, ClaimCategoryGroup, ClaimType
from app.models.company import Company
from app.models.document import Document, DocumentSection
from app.models.filing import SECFiling
from app.services.claims_service import ClaimsService

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
                section_type="business" if "1" in sec_id else "risk_factors",
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
        title="Apple Inc. Form 10-K",
        text=full_text,
        word_count=len(full_text.split()),
        sections=sections,
    )


# 1. Model & ID Tests
def test_claim_model_valid() -> None:
    claim_id = ClaimsService.generate_claim_id(
        company_ticker="AAPL",
        accession_number="0000320193-25-000079",
        section_id="item_1",
        claim_text="We aim to reduce emissions by 50% by 2030.",
    )
    assert claim_id.startswith("claim_aapl_0000320193_25_000079_")

    claim = Claim(
        claim_id=claim_id,
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text="We aim to reduce emissions by 50% by 2030.",
        claim_type="target",
        category="greenhouse_gas",
        category_group="environmental",
        source_type="sec_10k",
        source_title="Apple Inc. Form 10-K",
        source_url="https://example.com/filing.htm",
        filing_accession_number="0000320193-25-000079",
        filing_date="2025-10-31",
        report_date="2025-09-27",
        section_id="item_1",
        section_title="Item 1. Business",
        source_excerpt="We aim to reduce emissions by 50% by 2030.",
        source_location="Item 1. Business",
        target_year=2030,
        baseline_year=2020,
        metric="emissions",
        target_value="50%",
        unit="percent",
        confidence="high",
        status="validated",
    )
    assert claim.target_year == 2030
    assert claim.target_value == "50%"
    assert claim.unit == "percent"


def test_claim_id_stability() -> None:
    id1 = ClaimsService.generate_claim_id("AAPL", "0000320193-25-000079", "item_1", "Our operations are 100% renewable.")
    id2 = ClaimsService.generate_claim_id("AAPL", "0000320193-25-000079", "item_1", "Our operations are 100% renewable.")
    assert id1 == id2


# 2. Extraction & Categorization Tests
def test_extract_target_claim_with_quantification() -> None:
    service = ClaimsService()
    doc = create_mock_document([
        (
            "item_1",
            "Item 1. Business",
            "We aim to reduce greenhouse gas emissions by 50% by 2030 compared with our 2020 baseline.",
        )
    ])

    claims = service.extract_claims_from_document(MOCK_COMPANY, MOCK_FILING, doc)
    assert len(claims) == 1
    claim = claims[0]

    assert claim.claim_type == ClaimType.TARGET.value
    assert claim.category == "greenhouse_gas"
    assert claim.category_group == ClaimCategoryGroup.ENVIRONMENTAL.value
    assert claim.target_value == "50%"
    assert claim.target_year == 2030
    assert claim.baseline_year == 2020
    assert claim.unit == "percent"
    assert claim.confidence == "high"
    assert claim.status == "validated"


def test_extract_achievement_claim() -> None:
    service = ClaimsService()
    doc = create_mock_document([
        (
            "item_1",
            "Item 1. Business",
            "We achieved a 25% reduction in water consumption across all manufacturing campuses.",
        )
    ])

    claims = service.extract_claims_from_document(MOCK_COMPANY, MOCK_FILING, doc)
    assert len(claims) == 1
    claim = claims[0]

    assert claim.claim_type == ClaimType.ACHIEVEMENT.value
    assert claim.category == "water"
    assert claim.category_group == ClaimCategoryGroup.ENVIRONMENTAL.value
    assert claim.target_value == "25%"
    assert claim.target_year is None  # Not a future target year
    assert claim.confidence == "high"


def test_extract_policy_claim() -> None:
    service = ClaimsService()
    doc = create_mock_document([
        (
            "item_1",
            "Item 1. Business",
            "We maintain a supplier environmental policy that addresses environmental management and labor standards.",
        )
    ])

    claims = service.extract_claims_from_document(MOCK_COMPANY, MOCK_FILING, doc)
    assert len(claims) == 1
    claim = claims[0]

    assert claim.claim_type == ClaimType.POLICY.value
    assert claim.category == "environmental_management"
    assert claim.category_group == ClaimCategoryGroup.ENVIRONMENTAL.value
    assert claim.confidence == "medium"
    assert claim.status == "validated"


def test_extract_current_state_performance_claim() -> None:
    service = ClaimsService()
    doc = create_mock_document([
        (
            "item_1",
            "Item 1. Business",
            "Our operations are powered by 100% renewable energy across all corporate facilities worldwide.",
        )
    ])

    claims = service.extract_claims_from_document(MOCK_COMPANY, MOCK_FILING, doc)
    assert len(claims) == 1
    claim = claims[0]

    assert claim.claim_type == ClaimType.CURRENT_STATE.value
    assert claim.category == "renewable_energy"
    assert claim.target_value == "100%"
    assert claim.confidence == "high"


# 3. Filtering False Positives / Pure Risk Statements
def test_filter_pure_risk_statements() -> None:
    service = ClaimsService()
    doc = create_mock_document([
        (
            "item_1a",
            "Item 1A. Risk Factors",
            "Climate change may affect our operations and could materially adversely affect our supply chain.\n\n"
            "There can be no assurance that environmental regulations will not increase compliance costs.",
        )
    ])

    claims = service.extract_claims_from_document(MOCK_COMPANY, MOCK_FILING, doc)
    # Neither pure risk statement should become a claim
    assert len(claims) == 0


def test_filter_forward_looking_boilerplate() -> None:
    service = ClaimsService()
    doc = create_mock_document([
        (
            "item_7",
            "Item 7. MD&A",
            "Statements that are not historical facts are forward-looking statements regarding future environmental initiatives.",
        )
    ])

    claims = service.extract_claims_from_document(MOCK_COMPANY, MOCK_FILING, doc)
    assert len(claims) == 0


# 4. Deduplication & Additional Source Tracking
def test_deduplicate_repeated_claims_across_sections() -> None:
    service = ClaimsService()
    doc = create_mock_document([
        (
            "item_1",
            "Item 1. Business",
            "All corporate operations are powered by 100% renewable energy.",
        ),
        (
            "item_7",
            "Item 7. MD&A",
            "All corporate operations are powered by 100% renewable energy.",
        ),
    ])

    claims = service.extract_claims_from_document(MOCK_COMPANY, MOCK_FILING, doc)
    # Deduplication should preserve only 1 claim
    assert len(claims) == 1
    primary_claim = claims[0]

    # And link the second section occurrence as an additional source
    assert len(primary_claim.additional_sources) == 1
    add_source = primary_claim.additional_sources[0]
    assert add_source.section_id == "item_7"
    assert add_source.section_title == "Item 7. MD&A"


# 5. Source Traceability
def test_source_traceability_fields_present() -> None:
    service = ClaimsService()
    doc = create_mock_document([
        (
            "item_1",
            "Item 1. Business",
            "We plan to reach net-zero emissions by 2040.",
        )
    ])

    claims = service.extract_claims_from_document(MOCK_COMPANY, MOCK_FILING, doc)
    assert len(claims) == 1
    c = claims[0]

    assert c.company_ticker == "AAPL"
    assert c.company_name == "Apple Inc."
    assert c.filing_accession_number == "0000320193-25-000079"
    assert c.filing_date == "2025-10-31"
    assert c.report_date == "2025-09-27"
    assert c.section_id == "item_1"
    assert c.section_title == "Item 1. Business"
    assert c.source_url == MOCK_FILING.filing_url
    assert "net-zero" in c.source_excerpt


# 6. Non-Sustainability Disclosures Regression Tests
def test_filter_ordinary_legal_proceedings_and_defenses() -> None:
    service = ClaimsService()
    doc = create_mock_document([
        (
            "item_3",
            "Item 3. Legal Proceedings",
            "The Company believes it has substantial defenses and intends to vigorously defend itself.\n\n"
            "On January 16, 2024, the Company implemented a plan to comply with the 2021 Injunction and filed a statement of compliance.",
        )
    ])
    claims = service.extract_claims_from_document(MOCK_COMPANY, MOCK_FILING, doc)
    assert len(claims) == 0


def test_filter_dividend_and_financial_accounting() -> None:
    service = ClaimsService()
    doc = create_mock_document([
        (
            "item_7",
            "Item 7. MD&A",
            "The Company intends to increase its dividend on an annual basis, subject to declaration by the Board.\n\n"
            "ASU 2025-06 removes all references to software development stages and requires capitalization of software costs when management has committed to the software project.",
        ),
        (
            "item_8",
            "Item 8. Financial Statements",
            "For the Company’s Services net sales, control transfers over time as services are delivered.\n\n"
            "Revenue allocated to the delivered hardware and bundled software is recognized when control has transferred.\n\n"
            "Irish legislative changes, effective as of January 2015, eliminated the application of the tax opinions.",
        ),
    ])
    claims = service.extract_claims_from_document(MOCK_COMPANY, MOCK_FILING, doc)
    assert len(claims) == 0


def test_extract_equal_opportunity_policy_and_team_safety() -> None:
    service = ClaimsService()
    doc = create_mock_document([
        (
            "item_1",
            "Item 1. Business",
            "The Company is an equal opportunity employer committed to inclusion and to providing a workplace free of harassment or discrimination.\n\n"
            "The Company is committed to the safety and security of its team members everywhere it operates.",
        )
    ])
    claims = service.extract_claims_from_document(MOCK_COMPANY, MOCK_FILING, doc)
    assert len(claims) == 2

    # First claim: Equal opportunity policy
    c1 = next(c for c in claims if "equal opportunity" in c.claim_text.lower())
    assert c1.claim_type == ClaimType.POLICY
    assert c1.category == "inclusion"
    assert c1.category_group == ClaimCategoryGroup.SOCIAL

    # Second claim: Team member safety
    c2 = next(c for c in claims if "safety and security" in c.claim_text.lower())
    assert c2.category == "health_and_safety"
    assert c2.category_group == ClaimCategoryGroup.SOCIAL
