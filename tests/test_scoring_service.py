"""Tests for the Phase 8 ESG Integrity Scoring Engine.

Exact expected values are hand-computed from the documented methodology
(docs/ESG_INTEGRITY_SCORE_METHODOLOGY.md) so that formula regressions fail loudly.

Reference claim scores used throughout (no caveats unless stated):
    supported,   high confidence, cited relevance 0.45  -> 90 + 3 + 3 = 96
    partially,   medium confidence, relevance 0.35, 1 caveat -> 60 + 0 + 0 - 2 = 58
    unsubstantiated, medium confidence, no citation       -> 25 - 3 = 22
    inconsistent                                          -> 0 (fixed)
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models.company import Company
from app.models.evaluation import (
    AssessmentCategory,
    ClaimEvaluation,
    CompanyEvaluationResponse,
    EvaluationConfidence,
    EvaluationMode,
    EvaluationSummary,
    EvidenceReference,
)
from app.models.market import (
    DocumentSourceType,
    GSEAnalysisResponse,
    GSECompany,
    MarketDocument,
    MarketIdentifier,
)
from app.models.scoring import ConfidenceLevel, ScoreStatus
from app.services.scoring_service import QUANTITATIVE_PATTERN, ScoringService, get_scoring_service

A = AssessmentCategory
C = EvaluationConfidence

client = TestClient(app)


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def ref(ev_id: str = "ev_1", relevance: float = 0.45) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=ev_id,
        section_id="item_1",
        relevance_score=relevance,
        relationship="supporting",
        quote="Verbatim evidence excerpt.",
    )


def ev(
    claim_id: str,
    assessment: AssessmentCategory = A.SUPPORTED,
    *,
    text: str = "The company expanded its environmental programme.",
    claim_type: str = "achievement",
    category: str = "carbon",
    group: str = "environmental",
    confidence: EvaluationConfidence = None,
    caveats=None,
    refs=None,
    mode: EvaluationMode = EvaluationMode.RULE_BASED,
) -> ClaimEvaluation:
    """Build an evaluation. Defaults reproduce the reference scores in the module docstring."""
    defaults = {
        A.SUPPORTED: (C.HIGH, [ref(f"ev_{claim_id}", 0.45)], []),
        A.PARTIALLY_SUPPORTED: (C.MEDIUM, [ref(f"ev_{claim_id}", 0.35)], ["Scope limited to one site."]),
        A.UNSUBSTANTIATED: (C.MEDIUM, [], []),
        A.INCONSISTENT: (C.HIGH, [ref(f"ev_{claim_id}", 0.6)], []),
        A.INSUFFICIENT_EVIDENCE: (C.LOW, [], []),
    }
    d_conf, d_refs, d_cav = defaults[assessment]
    return ClaimEvaluation(
        evaluation_id=f"eval_{claim_id}",
        claim_id=claim_id,
        company_ticker="TEST",
        company_name="Test Corp",
        claim_text=text,
        claim_type=claim_type,
        category=category,
        category_group=group,
        assessment=assessment,
        confidence=confidence or d_conf,
        reasoning="Reasoning grounded in cited evidence.",
        caveats=d_cav if caveats is None else caveats,
        referenced_evidence=d_refs if refs is None else refs,
        evaluation_mode=mode,
    )


def score(evals, sector=None, market=MarketIdentifier.US_SEC, total=None, period=None, service=None):
    service = service or ScoringService()
    return service.calculate_score_from_evaluations(
        company_name="Test Corp",
        ticker="TEST",
        market=market,
        evaluations=evals,
        total_claims_extracted=len(evals) if total is None else total,
        reporting_period=period,
        sector=sector,
        source_document_references=["SEC EDGAR Form 10-K, accession 0000000000-26-000001"],
    )


# ─────────────────────────────────────────────────────────
# Claim-level scoring and assessment categories
# ─────────────────────────────────────────────────────────

def test_reference_claim_scores_exact():
    r = score([
        ev("s", A.SUPPORTED), ev("p", A.PARTIALLY_SUPPORTED),
        ev("u", A.UNSUBSTANTIATED), ev("i", A.INCONSISTENT),
    ])
    by_id = {c.claim_id: c for c in r.claim_scores}
    assert by_id["s"].claim_score == 96
    assert by_id["p"].claim_score == 58
    assert by_id["u"].claim_score == 22
    assert by_id["i"].claim_score == 0
    assert by_id["s"].quality_adjustment_reasons  # adjustments are explained


def test_strongly_supported_company():
    r = score([ev(f"s{i}", A.SUPPORTED) for i in range(5)])
    assert r.score_status == ScoreStatus.SCORED
    assert r.esg_integrity_score == 96
    assert r.supported_claims == 5
    assert r.substantiation_rate == 100


def test_partially_supported_company():
    r = score([ev(f"p{i}", A.PARTIALLY_SUPPORTED) for i in range(4)])
    assert r.esg_integrity_score == 58
    assert r.partially_supported_claims == 4
    assert any("Partially supported" in p for p in r.main_positive_factors)


def test_mixed_company_exact_weighted_score():
    # Single pillar, equal weights (1.5 achievement, unquantified): (96 + 58 + 22) / 3 = 58.67 -> 59
    r = score([ev("s", A.SUPPORTED), ev("p", A.PARTIALLY_SUPPORTED), ev("u", A.UNSUBSTANTIATED)])
    assert r.esg_integrity_score == 59


def test_contradictory_evidence_company():
    r = score([ev(f"i{i}", A.INCONSISTENT) for i in range(3)])
    assert r.esg_integrity_score == 0
    assert r.inconsistent_claims == 3
    assert sum("Contradicted" in c for c in r.main_concerns) == 3


def test_inconsistent_not_rescued_by_evidence_quality():
    r = score([ev("i", A.INCONSISTENT, confidence=C.HIGH, refs=[ref("x", 0.99)])])
    assert r.claim_scores[0].claim_score == 0
    assert r.claim_scores[0].evidence_quality_adjustment == 0


def test_unsubstantiated_is_partial_credit_not_false():
    r = score([ev(f"u{i}", A.UNSUBSTANTIATED) for i in range(3)])
    assert r.esg_integrity_score == 22  # strictly above inconsistent (0)
    concern = next(c for c in r.main_concerns if c.startswith("Unsubstantiated"))
    assert "not a finding that the claim is false" in concern


def test_insufficient_evidence_excluded_from_score_and_reduces_coverage():
    base = score([ev(f"s{i}") for i in range(3)])
    with_insufficient = score([ev(f"s{i}") for i in range(3)] + [ev("x", A.INSUFFICIENT_EVIDENCE)])
    with_inconsistent = score([ev(f"s{i}") for i in range(3)] + [ev("x", A.INCONSISTENT)])

    assert with_insufficient.esg_integrity_score == base.esg_integrity_score == 96
    assert with_insufficient.evidence_coverage == 75
    assert with_inconsistent.esg_integrity_score < with_insufficient.esg_integrity_score
    assert with_insufficient.insufficient_evidence_claims == 1
    assert next(c for c in with_insufficient.claim_scores if c.claim_id == "x").included_in_score is False


def test_assessment_bands_do_not_overlap():
    best_partial = score([ev("p", A.PARTIALLY_SUPPORTED, confidence=C.HIGH, refs=[ref("e", 0.9)], caveats=[])])
    worst_supported = score([ev("s", A.SUPPORTED, confidence=C.LOW, refs=[ref("e", 0.1)], caveats=["a", "b", "c"])])
    best_unsub = score([ev("u", A.UNSUBSTANTIATED, confidence=C.HIGH, refs=[ref("e", 0.9)])])
    assert best_partial.claim_scores[0].claim_score == 66
    assert worst_supported.claim_scores[0].claim_score == 80
    assert best_unsub.claim_scores[0].claim_score == 31
    assert worst_supported.claim_scores[0].claim_score > best_partial.claim_scores[0].claim_score
    assert best_partial.claim_scores[0].claim_score > best_unsub.claim_scores[0].claim_score


def test_supported_claim_without_citation_is_penalised():
    r = score([ev("s", A.SUPPORTED, refs=[])])
    assert r.claim_scores[0].claim_score == 90  # 90 + 3 (high conf) - 3 (no citation)


# ─────────────────────────────────────────────────────────
# Missing information / insufficient data
# ─────────────────────────────────────────────────────────

def test_no_sustainability_claims_returns_insufficient_data_not_zero():
    r = score([], total=0)
    assert r.score_status == ScoreStatus.INSUFFICIENT_DATA
    assert r.esg_integrity_score is None
    assert r.confidence == ConfidenceLevel.INSUFFICIENT
    assert r.evidence_coverage == 0
    assert r.substantiation_rate is None
    assert all(d.score is None for d in r.dimensions.values())


def test_all_insufficient_evidence_returns_insufficient_data():
    r = score([ev(f"x{i}", A.INSUFFICIENT_EVIDENCE) for i in range(5)])
    assert r.score_status == ScoreStatus.INSUFFICIENT_DATA
    assert r.esg_integrity_score is None
    assert r.evidence_coverage == 0


def test_below_minimum_assessable_claims_returns_insufficient_data():
    r = score([ev("s1"), ev("s2")])
    assert r.score_status == ScoreStatus.INSUFFICIENT_DATA
    assert r.esg_integrity_score is None
    assert "at least 3" in r.main_concerns[0]


def test_missing_dimension_is_not_zero():
    r = score([ev(f"e{i}") for i in range(3)] + [ev(f"s{i}", group="social", category="diversity") for i in range(3)])
    gov = r.dimensions["governance"]
    assert r.governance_score is None
    assert gov.status == ScoreStatus.INSUFFICIENT_DATA
    assert gov.effective_weight == 0
    assert r.esg_integrity_score == 96  # unaffected by the missing pillar
    assert any("Governance" in c and "not zero" in c for c in r.main_concerns)


def test_claims_across_all_three_dimensions():
    r = score(
        [ev(f"e{i}") for i in range(3)]
        + [ev(f"s{i}", A.PARTIALLY_SUPPORTED, group="social", category="diversity") for i in range(3)]
        + [ev(f"g{i}", A.UNSUBSTANTIATED, group="governance", category="board") for i in range(3)]
    )
    assert (r.environmental_score, r.social_score, r.governance_score) == (96, 58, 22)
    # (0.40*96 + 0.35*58 + 0.25*22) / 1.0 = 64.2 -> 64
    assert r.esg_integrity_score == 64
    assert sum(d.effective_weight for d in r.dimensions.values()) == pytest.approx(1.0, abs=0.002)


def test_configured_pillar_weights_are_applied():
    r = score([ev(f"e{i}") for i in range(3)] + [ev(f"s{i}", A.INCONSISTENT, group="social") for i in range(3)])
    # (0.40*96 + 0.35*0) / 0.75 = 51.2 -> 51 (an unweighted claim average would give 48)
    assert r.esg_integrity_score == 51


def test_thinly_evidenced_pillar_is_down_weighted():
    r = score([ev(f"e{i}") for i in range(3)] + [ev("g1", A.INCONSISTENT, group="governance")])
    # Governance weight 0.25 * (1/3): (0.40*96) / (0.40 + 0.0833) = 79.4 -> 79
    assert r.esg_integrity_score == 79
    assert r.dimensions["governance"].confidence == ConfidenceLevel.LOW


def test_unmapped_category_excluded_and_reported():
    r = score([ev(f"e{i}") for i in range(3)] + [ev("o1", A.INCONSISTENT, group="other")])
    assert r.unmapped_claims == 1
    assert r.esg_integrity_score == 96


# ─────────────────────────────────────────────────────────
# Materiality and volume damping
# ─────────────────────────────────────────────────────────

def test_few_highly_material_claims_dominate_generic_statements():
    material = [
        ev(f"m{i}", A.INCONSISTENT, text="Reduced total corporate carbon emissions by half.", claim_type="achievement")
        for i in range(2)
    ]
    boilerplate = [
        ev(f"g{i}", A.SUPPORTED, text=f"We care about the environment, statement {i}.", claim_type="general",
           category="sustainability")
        for i in range(200)
    ]
    r = score(material + boilerplate)
    # High weight 3.0; low weight 120 capped at 25% of total weight => cap = 3.0 * 0.25 / 0.75 = 1.0
    # Score = (3.0*0 + 1.0*96) / 4.0 = 24
    assert r.esg_integrity_score == 24
    assert any("Volume damping" in f for f in r.dimensions["environmental"].key_factors)


def test_publishing_more_statements_does_not_raise_score():
    material = [ev(f"m{i}", A.UNSUBSTANTIATED, claim_type="target") for i in range(3)]
    few = score(material + [ev(f"g{i}", claim_type="general") for i in range(3)])
    many = score(material + [ev(f"g{i}", claim_type="general") for i in range(300)])
    assert many.esg_integrity_score == few.esg_integrity_score


def test_quantified_and_target_year_detection_ignores_report_headers():
    assert QUANTITATIVE_PATTERN.search("We reduced emissions by 15.8% versus 2021.")
    assert QUANTITATIVE_PATTERN.search("We will reach net zero by 2030.")
    assert QUANTITATIVE_PATTERN.search("Trained 5,000 employees in safety.")
    assert QUANTITATIVE_PATTERN.search("Invested GH₵ 12 million in schools.")
    assert not QUANTITATIVE_PATTERN.search("Scancom PLC 2024 Annual Report: we are committed to communities.")


def test_quantified_claim_gets_higher_weight():
    r = score([ev("q", text="Cut emissions by 20%."), ev("n", text="Cut emissions substantially."), ev("x")])
    w = {c.claim_id: c.materiality_weight for c in r.claim_scores}
    assert w["q"] == pytest.approx(1.8)
    assert w["n"] == pytest.approx(1.5)


# ─────────────────────────────────────────────────────────
# Sectors, Ghana and US
# ─────────────────────────────────────────────────────────

def test_mining_sector_boosts_water_and_rehabilitation_claims():
    evals = [
        ev("w", category="water", text="Recycled water at the tailings facility."),
        ev("r", category="environmental_management", text="Completed land rehabilitation of mined areas."),
        ev("x", category="diversity", group="social", text="Hosted a staff diversity forum."),
    ]
    r = score(evals, sector="Mining", market=MarketIdentifier.GH_GSE)
    m = {c.claim_id: c.sector_priority_match for c in r.claim_scores}
    assert m == {"w": True, "r": True, "x": False}
    assert r.materiality_summary["matched_sector_profile"] == "mining"


def test_mining_criteria_not_applied_to_banks_or_telecoms():
    evals = [ev("w", category="water", text="Recycled water at the tailings facility."), ev("a"), ev("b")]
    for sector in ("Banking", "Telecommunications"):
        r = score(evals, sector=sector, market=MarketIdentifier.GH_GSE)
        assert next(c for c in r.claim_scores if c.claim_id == "w").sector_priority_match is False


def test_telecom_ghana_keywords_boost():
    r = score(
        [ev("e", category="community", group="social", text="Our e-waste programme collected old handsets."),
         ev("a"), ev("b")],
        sector="Telecommunications",
        market=MarketIdentifier.GH_GSE,
    )
    assert next(c for c in r.claim_scores if c.claim_id == "e").sector_priority_match is True


def test_us_sic_sector_profile_matches():
    r = score([ev("r", category="renewable_energy"), ev("a"), ev("b")], sector="Electronic Computers")
    assert r.materiality_summary["matched_sector_profile"] == "technology"
    assert r.claim_scores[0].sector_priority_match is True


def test_unknown_sector_applies_no_boost():
    r = score([ev("w", category="water"), ev("a"), ev("b")], sector="Real Estate Investment Trusts")
    assert r.materiality_summary["matched_sector_profile"] is None
    assert not any(c.sector_priority_match for c in r.claim_scores)


def test_same_inputs_score_identically_in_both_markets():
    evals = [ev(f"e{i}") for i in range(3)] + [ev("u", A.UNSUBSTANTIATED, group="social")]
    us = score(evals, sector="Mining", market=MarketIdentifier.US_SEC)
    gh = score(evals, sector="Mining", market=MarketIdentifier.GH_GSE)
    assert us.esg_integrity_score == gh.esg_integrity_score
    assert [c.materiality_weight for c in us.claim_scores] == [c.materiality_weight for c in gh.claim_scores]
    assert (us.market, gh.market) == (MarketIdentifier.US_SEC, MarketIdentifier.GH_GSE)


def test_reporting_period_preserved():
    evals = [ev(f"s{i}") for i in range(3)]
    assert score(evals, period="2023").reporting_period == "2023"
    assert score(evals, period="FY2024").reporting_period == "FY2024"


# ─────────────────────────────────────────────────────────
# Confidence and coverage
# ─────────────────────────────────────────────────────────

def test_confidence_low_with_few_claims():
    assert score([ev(f"s{i}") for i in range(3)]).confidence == ConfidenceLevel.LOW


def test_confidence_medium_with_moderate_sample():
    assert score([ev(f"s{i}") for i in range(5)]).confidence == ConfidenceLevel.MEDIUM


def test_confidence_capped_for_rule_based_evaluations():
    evals = [ev(f"e{i}") for i in range(6)] + [ev(f"s{i}", group="social") for i in range(6)]
    r = score(evals)
    assert r.confidence == ConfidenceLevel.MEDIUM
    assert r.rule_based_evaluations == 12
    assert any("rule-based" in c for c in r.main_concerns)


def test_confidence_high_requires_llm_sample_coverage_and_breadth():
    evals = [ev(f"e{i}", mode=EvaluationMode.LLM) for i in range(6)] + [
        ev(f"s{i}", group="social", mode=EvaluationMode.LLM) for i in range(6)
    ]
    assert score(evals).confidence == ConfidenceLevel.HIGH
    # Same claims in a single pillar: not enough breadth for HIGH
    single = [ev(f"e{i}", mode=EvaluationMode.LLM) for i in range(12)]
    assert score(single).confidence == ConfidenceLevel.MEDIUM


def test_low_coverage_lowers_confidence():
    evals = [ev(f"s{i}", mode=EvaluationMode.LLM) for i in range(10)] + [
        ev(f"x{i}", A.INSUFFICIENT_EVIDENCE, mode=EvaluationMode.LLM) for i in range(15)
    ]
    r = score(evals)
    assert r.evidence_coverage == 40
    assert r.confidence == ConfidenceLevel.LOW


def test_coverage_is_not_described_as_corroboration():
    r = score([ev(f"u{i}", A.UNSUBSTANTIATED) for i in range(5)])
    assert r.evidence_coverage == 100
    assert r.substantiation_rate == 0
    assert not any("corroborat" in p.lower() for p in r.main_positive_factors)
    assert any("Only 0%" in c for c in r.main_concerns)


# ─────────────────────────────────────────────────────────
# Integrity, determinism, boundaries, invalid data
# ─────────────────────────────────────────────────────────

def test_deterministic_repeatability():
    evals = [ev("s"), ev("p", A.PARTIALLY_SUPPORTED), ev("i", A.INCONSISTENT, group="social"),
             ev("u", A.UNSUBSTANTIATED, group="governance")]
    a = score(evals, sector="Mining").model_dump(exclude={"assessment_timestamp"})
    b = score(evals, sector="Mining").model_dump(exclude={"assessment_timestamp"})
    assert a == b


def test_score_boundaries_and_whole_number_rounding():
    top = score([ev(f"s{i}", confidence=C.HIGH, refs=[ref("e", 1.0)]) for i in range(3)])
    bottom = score([ev(f"i{i}", A.INCONSISTENT) for i in range(3)])
    assert 0 <= bottom.esg_integrity_score <= top.esg_integrity_score <= 100
    assert bottom.esg_integrity_score == 0
    for r in (top, bottom):
        assert r.esg_integrity_score == int(r.esg_integrity_score)


def test_evidence_traceability():
    r = score([ev("claim_abc", refs=[ref("ev_123"), ref("ev_456")]), ev("b"), ev("c")])
    d = next(c for c in r.claim_scores if c.claim_id == "claim_abc")
    assert d.evaluation_id == "eval_claim_abc"
    assert d.referenced_evidence_ids == ["ev_123", "ev_456"]
    assert "0000000000-26-000001" in r.source_document_references[0]
    assert any("[claim_abc]" in p for p in r.main_positive_factors)


def test_duplicate_claim_evaluations_counted_once():
    r = score([ev("dup"), ev("dup"), ev("b"), ev("c")])
    assert r.total_claims_assessed == 3
    assert r.duplicate_evaluations_ignored == 1


def test_unknown_claim_type_treated_as_general():
    r = score([ev("x", claim_type="aspiration"), ev("a"), ev("b")])
    assert next(c for c in r.claim_scores if c.claim_id == "x").materiality_weight == pytest.approx(0.6)


def test_incomplete_evaluation_data_rejected_by_model():
    with pytest.raises(ValidationError):
        ClaimEvaluation(claim_id="c", company_ticker="T", company_name="T", claim_text="x")
    with pytest.raises(ValidationError):
        ev("c").model_copy(update={}).__class__(**{**ev("c").model_dump(), "assessment": "greenwashing"})


def test_disclaimer_present():
    r = score([ev(f"s{i}") for i in range(3)])
    assert "does not" in r.disclaimer.lower() and "greenwashing" in r.disclaimer.lower()


# ─────────────────────────────────────────────────────────
# Service integration (SEC + GSE) with mocked upstream services
# ─────────────────────────────────────────────────────────

def sec_eval_response(evals, fiscal_year=2026, report_date="2026-09-26", accession="0000320193-26-000026"):
    return CompanyEvaluationResponse(
        company=Company(ticker="AAPL", company_name="Apple Inc.", cik="0000320193",
                        sic="3571", sic_description="Electronic Computers"),
        filing_accession_number=accession,
        form_type="10-K",
        filing_date="2026-11-03",
        report_date=report_date,
        fiscal_year=fiscal_year,
        summary=EvaluationSummary(total_claims_evaluated=len(evals), total_claims_extracted=len(evals) + 2),
        evaluations=evals,
        provider_mode="rule_based",
    )


def gse_analysis_response(evals, period="2024", doc_id="doc_gse_mtngh_2024"):
    return GSEAnalysisResponse(
        company=GSECompany(ticker="MTNGH", company_name="Scancom Plc", market=MarketIdentifier.GH_GSE,
                           sector="Telecommunications", industry="Mobile Telecommunications"),
        document=MarketDocument(
            document_id=doc_id, company_ticker="MTNGH", company_name="Scancom Plc",
            market=MarketIdentifier.GH_GSE, source_type=DocumentSourceType.ANNUAL_REPORT,
            title=f"Scancom PLC (MTN Ghana) {period} Annual Report", reporting_period=period,
            source_url="https://mtn.com.gh/report.pdf", retrieval_status="retrieved", format="pdf",
        ),
        total_claims_extracted=len(evals) + 2,
        evaluations=evals,
        summary=EvaluationSummary(total_claims_evaluated=len(evals), total_claims_extracted=len(evals) + 2),
        provider_mode="rule_based",
    )


def make_service(sec_resp=None, gse_resp=None):
    llm = MagicMock()
    llm.evaluate_company_filing.return_value = sec_resp
    gse = MagicMock()
    gse.analyze_company_document.return_value = gse_resp
    return ScoringService(llm_service=llm, gse_service=gse), llm, gse


def test_sec_company_uses_fiscal_period_and_filing_reference():
    svc, _, _ = make_service(sec_resp=sec_eval_response([ev(f"s{i}") for i in range(3)]))
    r = svc.calculate_company_score("aapl")
    assert r.market == MarketIdentifier.US_SEC
    assert r.reporting_period == "FY2026"
    assert r.total_claims_extracted == 5
    assert "0000320193-26-000026" in r.source_document_references[0]
    assert r.materiality_summary["matched_sector_profile"] == "technology"


def test_sec_reporting_period_not_invented_when_unknown():
    svc, _, _ = make_service(sec_resp=sec_eval_response([ev(f"s{i}") for i in range(3)],
                                                        fiscal_year=None, report_date=None))
    assert svc.calculate_company_score("AAPL").reporting_period is None


def test_gse_company_scoring_and_sources():
    svc, _, gse = make_service(gse_resp=gse_analysis_response([ev(f"s{i}") for i in range(3)]))
    r = svc.calculate_gse_score("mtngh")
    assert r.market == MarketIdentifier.GH_GSE
    assert r.reporting_period == "2024"
    assert "doc_gse_mtngh_2024" in r.source_document_references[0]
    assert "https://mtn.com.gh/report.pdf" in r.source_document_references
    assert gse.analyze_company_document.call_args.kwargs["ticker"] == "MTNGH"


def test_history_only_contains_real_assessments_one_per_document():
    svc, _, gse = make_service(gse_resp=gse_analysis_response([ev(f"s{i}") for i in range(3)]))
    assert svc.get_company_score_history("MTNGH", MarketIdentifier.GH_GSE).total_records == 0

    svc.calculate_gse_score("MTNGH")
    svc.calculate_gse_score("MTNGH")  # same document re-scored: replaces, not duplicates
    assert svc.get_company_score_history("MTNGH", MarketIdentifier.GH_GSE).total_records == 1

    gse.analyze_company_document.return_value = gse_analysis_response(
        [ev(f"u{i}", A.UNSUBSTANTIATED) for i in range(3)], period="2023", doc_id="doc_gse_mtngh_2023")
    svc.calculate_gse_score("MTNGH", reporting_period="2023")
    hist = svc.get_company_score_history("MTNGH", MarketIdentifier.GH_GSE)
    assert hist.total_records == 2
    assert [h.reporting_period for h in hist.history] == ["2023", "2024"]
    assert [h.esg_integrity_score for h in hist.history] == [22, 96]


def test_market_caches_are_isolated():
    svc, _, _ = make_service(
        sec_resp=sec_eval_response([ev(f"s{i}") for i in range(3)]),
        gse_resp=gse_analysis_response([ev(f"i{i}", A.INCONSISTENT) for i in range(3)]),
    )
    svc.calculate_company_score("AAPL")
    svc.calculate_gse_score("MTNGH")
    assert svc.get_company_score("AAPL", MarketIdentifier.US_SEC).esg_integrity_score == 96
    assert svc.get_company_score("MTNGH", MarketIdentifier.GH_GSE).esg_integrity_score == 0
    assert svc.get_company_score_history("AAPL", MarketIdentifier.GH_GSE).total_records == 0


# ─────────────────────────────────────────────────────────
# API endpoints (isolated service via dependency override)
# ─────────────────────────────────────────────────────────

@pytest.fixture
def api_service():
    svc, llm, gse = make_service(
        sec_resp=sec_eval_response([ev(f"s{i}") for i in range(3)] + [ev("u", A.UNSUBSTANTIATED, group="social")]),
        gse_resp=gse_analysis_response([ev(f"s{i}") for i in range(3)]),
    )
    app.dependency_overrides[get_scoring_service] = lambda: svc
    yield svc, llm, gse
    app.dependency_overrides.pop(get_scoring_service, None)


def test_api_company_score(api_service):
    resp = client.get("/api/v1/companies/AAPL/score")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "AAPL" and data["market"] == "us_sec"
    assert data["score_status"] == "scored"
    # E pillar = 96 (weight 0.40); S pillar = 22 (1 claim -> weight 0.35 * 1/3 = 0.1167) => 79.3 -> 79
    assert data["esg_integrity_score"] == 79
    assert data["reporting_period"] == "FY2026"
    assert "claim_scores" not in data
    assert data["disclaimer"]


def test_api_company_score_breakdown(api_service):
    data = client.get("/api/v1/companies/AAPL/score/breakdown").json()
    assert set(data["dimensions"]) == {"environmental", "social", "governance"}
    assert {c["claim_id"] for c in data["claim_scores"]} == {"s0", "s1", "s2", "u"}
    assert data["methodology_details"]["min_assessable_claims"] == 3


def test_api_company_score_history(api_service):
    empty = client.get("/api/v1/companies/AAPL/score/history").json()
    assert empty["total_records"] == 0 and empty["history"] == []
    client.get("/api/v1/companies/AAPL/score")
    hist = client.get("/api/v1/companies/AAPL/score/history").json()
    assert hist["total_records"] == 1
    assert "fabricated" in hist["note"]


def test_api_company_score_invalid_ticker(api_service):
    assert client.get("/api/v1/companies/@@@/score").status_code == 400
    assert client.get("/api/v1/companies/@@@/score/history").status_code == 400


def test_api_insufficient_data_returns_null_score(api_service):
    svc, llm, _ = api_service
    llm.evaluate_company_filing.return_value = sec_eval_response([ev("x", A.INSUFFICIENT_EVIDENCE)])
    data = client.get("/api/v1/companies/AAPL/score").json()
    assert data["score_status"] == "insufficient_data"
    assert data["esg_integrity_score"] is None
    assert data["confidence"] == "insufficient"


def test_api_gse_score_and_breakdown(api_service):
    data = client.get("/api/v1/gse/companies/MTNGH/score").json()
    assert data["market"] == "gh_gse" and data["esg_integrity_score"] == 96
    breakdown = client.get("/api/v1/gse/companies/MTNGH/score/breakdown").json()
    assert breakdown["materiality_summary"]["matched_sector_profile"] == "telecommunications"
    assert breakdown["materiality_summary"]["sector"] == "Telecommunications"


def test_api_gse_score_with_explicit_document(api_service):
    _, _, gse = api_service
    resp = client.get("/api/v1/gse/companies/MTNGH/score",
                      params={"source_url": "https://mtn.com.gh/r.pdf", "reporting_period": "2024"})
    assert resp.status_code == 200
    assert gse.analyze_company_document.call_args.kwargs["source_url"] == "https://mtn.com.gh/r.pdf"


def test_api_gse_score_history(api_service):
    client.get("/api/v1/gse/companies/MTNGH/score")
    data = client.get("/api/v1/gse/companies/MTNGH/score/history").json()
    assert data["market"] == "gh_gse" and data["total_records"] == 1
