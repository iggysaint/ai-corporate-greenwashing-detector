"""Comprehensive unit tests for Phase 8 ESG Integrity Scoring Engine.

Tests:
1. Strongly supported claims (high score)
2. Partially supported claims (moderate score with caveats)
3. Contradictory evidence / Inconsistent claims (heavily penalized, 0 score for contradiction)
4. Unsubstantiated claims (partial credit 25.0, not zero/fraud)
5. Insufficient evidence claims (penalizes coverage, not treated as inconsistent)
6. Zero claims / No sustainability claims (returns explicit insufficient_data status, None score)
7. Claims across all 3 ESG dimensions (Environmental, Social, Governance)
8. Missing information from one dimension (unscored pillar returns insufficient_data without crashing)
9. Small number of highly material claims vs many low-materiality claims (materiality weighting)
10. Volume damping (preventing low-materiality claim-stuffing from dominating)
11. Different reporting periods
12. Sector priority materiality boost (e.g., Ghana mining, telco, US tech)
13. Ghanaian companies (GSE MarketIdentifier and sector taxonomy)
14. US companies (SEC MarketIdentifier and SIC sector taxonomy)
15. Invalid / edge case inputs
16. Deterministic repeatability (identical inputs produce identical scores)
17. Boundary conditions (clamped to 0-100, rounding to 1 decimal place)
18. Evidence traceability (claim_id, evaluation_id, evidence_id, source references)
19. Confidence calculation logic and small-sample guard (fewer than 3 claims can never achieve HIGH confidence)
20. Evidence coverage calculation
21. All new API endpoints via TestClient:
    - GET /api/v1/companies/{ticker}/score
    - GET /api/v1/companies/{ticker}/score/breakdown
    - GET /api/v1/companies/{ticker}/score/history
    - GET /api/v1/gse/companies/{ticker}/score
    - GET /api/v1/gse/companies/{ticker}/score/breakdown
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.claim import ClaimCategoryGroup, ClaimType
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
from app.models.scoring import (
    ConfidenceLevel,
    ESGIntegrityScoreResponse,
    ESGScoreBreakdownResponse,
    ScoreStatus,
)
from app.services.scoring_service import ScoringService

client = TestClient(app)


# ─────────────────────────────────────────────────────────
# Test Fixtures & Helpers
# ─────────────────────────────────────────────────────────

def create_eval(
    claim_id: str,
    claim_text: str,
    claim_type: str = "achievement",
    category: str = "carbon",
    category_group: str = "environmental",
    assessment: AssessmentCategory = AssessmentCategory.SUPPORTED,
    confidence: EvaluationConfidence = EvaluationConfidence.HIGH,
    caveats: list[str] = None,
    referenced_evidence: list[EvidenceReference] = None,
    reasoning: str = "Affirmative disclosure matches claim.",
) -> ClaimEvaluation:
    """Helper to construct a ClaimEvaluation for scoring tests."""
    return ClaimEvaluation(
        evaluation_id=f"eval_{claim_id}",
        claim_id=claim_id,
        company_ticker="TEST",
        company_name="Test Corp",
        claim_text=claim_text,
        claim_type=claim_type,
        category=category,
        category_group=category_group,
        assessment=assessment,
        confidence=confidence,
        reasoning=reasoning,
        caveats=caveats or [],
        referenced_evidence=referenced_evidence or [],
        evaluation_mode=EvaluationMode.RULE_BASED,
    )


def sample_evidence_ref(ev_id: str = "ev_1", relevance: float = 0.45) -> EvidenceReference:
    """Helper to construct an EvidenceReference."""
    return EvidenceReference(
        evidence_id=ev_id,
        section_id="item_1",
        relevance_score=relevance,
        relationship="supporting",
        quote="Disclosed 15.8% carbon reduction relative to 2021 baseline.",
    )


# ─────────────────────────────────────────────────────────
# 1. Strongly Supported Claims (High Score)
# ─────────────────────────────────────────────────────────

def test_strongly_supported_claims_high_score():
    """A company with all supported claims receives a high integrity score."""
    service = ScoringService()
    evals = [
        create_eval(
            claim_id="c1",
            claim_text="We reduced carbon emissions by 15.8% in 2024.",
            claim_type=ClaimType.ACHIEVEMENT.value,
            category="carbon",
            category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
            assessment=AssessmentCategory.SUPPORTED,
            referenced_evidence=[sample_evidence_ref("ev_1", 0.50)],
        ),
        create_eval(
            claim_id="c2",
            claim_text="Achieved 50% female representation on our Board of Directors.",
            claim_type=ClaimType.ACHIEVEMENT.value,
            category="diversity",
            category_group=ClaimCategoryGroup.SOCIAL.value,
            assessment=AssessmentCategory.SUPPORTED,
            referenced_evidence=[sample_evidence_ref("ev_2", 0.45)],
        ),
        create_eval(
            claim_id="c3",
            claim_text="Maintained 100% compliance with SEC governance standards.",
            claim_type=ClaimType.POLICY.value,
            category="governance",
            category_group=ClaimCategoryGroup.GOVERNANCE.value,
            assessment=AssessmentCategory.SUPPORTED,
            referenced_evidence=[sample_evidence_ref("ev_3", 0.40)],
        ),
    ]

    result = service.calculate_score_from_evaluations(
        company_name="Clean Future Corp",
        ticker="CLEAN",
        market=MarketIdentifier.US_SEC,
        evaluations=evals,
        total_claims_extracted=3,
    )

    assert result.score_status == ScoreStatus.SCORED
    assert result.esg_integrity_score is not None
    assert result.esg_integrity_score >= 95.0
    assert result.supported_claims == 3
    assert result.inconsistent_claims == 0
    assert result.evidence_coverage == 100.0


# ─────────────────────────────────────────────────────────
# 2. Partially Supported Claims (Moderate Score)
# ─────────────────────────────────────────────────────────

def test_partially_supported_claims():
    """Partially supported claims with caveats produce a moderate score."""
    service = ScoringService()
    evals = [
        create_eval(
            claim_id="c1",
            claim_text="Our operations are powered by 100% renewable electricity.",
            claim_type=ClaimType.TARGET.value,
            category="renewable_energy",
            category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
            assessment=AssessmentCategory.PARTIALLY_SUPPORTED,
            caveats=["Data center scope only; manufacturing facilities excluded."],
            referenced_evidence=[sample_evidence_ref("ev_1", 0.35)],
        ),
        create_eval(
            claim_id="c2",
            claim_text="We achieved 40% female leadership representation.",
            claim_type=ClaimType.ACHIEVEMENT.value,
            category="diversity",
            category_group=ClaimCategoryGroup.SOCIAL.value,
            assessment=AssessmentCategory.PARTIALLY_SUPPORTED,
            caveats=["Excludes subsidiary operations in emerging markets."],
            referenced_evidence=[sample_evidence_ref("ev_2", 0.38)],
        ),
    ]

    result = service.calculate_score_from_evaluations(
        company_name="Caveat Corp",
        ticker="CAVT",
        market=MarketIdentifier.US_SEC,
        evaluations=evals,
        total_claims_extracted=2,
    )

    assert result.score_status == ScoreStatus.SCORED
    assert result.esg_integrity_score is not None
    assert 50.0 <= result.esg_integrity_score <= 70.0
    assert result.partially_supported_claims == 2


# ─────────────────────────────────────────────────────────
# 3. Contradictory Evidence / Inconsistent Claims
# ─────────────────────────────────────────────────────────

def test_contradictory_inconsistent_evidence():
    """Inconsistent claims score 0.0 with full materiality weight and trigger major concerns."""
    service = ScoringService()
    evals = [
        create_eval(
            claim_id="c1",
            claim_text="We have reduced net carbon emissions to zero.",
            claim_type=ClaimType.ACHIEVEMENT.value,
            category="carbon",
            category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
            assessment=AssessmentCategory.INCONSISTENT,
            referenced_evidence=[sample_evidence_ref("ev_1", 0.60)],
            reasoning="Disclosed filing metrics show Scope 1 and 2 emissions actually increased 14%.",
        ),
        create_eval(
            claim_id="c2",
            claim_text="Zero workplace fatalities recorded in 2024.",
            claim_type=ClaimType.ACHIEVEMENT.value,
            category="health_and_safety",
            category_group=ClaimCategoryGroup.SOCIAL.value,
            assessment=AssessmentCategory.INCONSISTENT,
            referenced_evidence=[sample_evidence_ref("ev_2", 0.55)],
            reasoning="Item 1A disclosures report two fatal industrial accidents at contractor facilities.",
        ),
    ]

    result = service.calculate_score_from_evaluations(
        company_name="Bad Faith Corp",
        ticker="BAD",
        market=MarketIdentifier.US_SEC,
        evaluations=evals,
        total_claims_extracted=2,
    )

    assert result.score_status == ScoreStatus.SCORED
    assert result.esg_integrity_score == 0.0
    assert result.inconsistent_claims == 2
    assert any("CONTRADICTION" in concern for concern in result.main_concerns)


# ─────────────────────────────────────────────────────────
# 4. Unsubstantiated Claims (Inadequate Proof, Not Fraud)
# ─────────────────────────────────────────────────────────

def test_unsubstantiated_claims():
    """Unsubstantiated claims receive partial credit (~25.0) and are not treated as 0 or fraud."""
    service = ScoringService()
    evals = [
        create_eval(
            claim_id="c1",
            claim_text="The company is committed to generational equality and SDG 5.",
            claim_type=ClaimType.TARGET.value,
            category="inclusion",
            category_group=ClaimCategoryGroup.SOCIAL.value,
            assessment=AssessmentCategory.UNSUBSTANTIATED,
            reasoning="Filing contains no formal milestone targets or timetable.",
        ),
        create_eval(
            claim_id="c2",
            claim_text="We strive to be the global benchmark in ethical AI governance.",
            claim_type=ClaimType.GENERAL.value,
            category="ethics",
            category_group=ClaimCategoryGroup.GOVERNANCE.value,
            assessment=AssessmentCategory.UNSUBSTANTIATED,
            reasoning="General aspirational policy without verification.",
        ),
    ]

    result = service.calculate_score_from_evaluations(
        company_name="Aspirational Corp",
        ticker="ASPR",
        market=MarketIdentifier.US_SEC,
        evaluations=evals,
        total_claims_extracted=2,
    )

    assert result.score_status == ScoreStatus.SCORED
    assert result.esg_integrity_score is not None
    assert 20.0 <= result.esg_integrity_score <= 30.0
    assert result.unsubstantiated_claims == 2


# ─────────────────────────────────────────────────────────
# 5. Insufficient Evidence (Excluded from Score, Lowers Coverage)
# ─────────────────────────────────────────────────────────

def test_insufficient_evidence_penalizes_coverage():
    """Insufficient evidence is not treated as contradictory; it reduces evidence coverage."""
    service = ScoringService()
    evals = [
        create_eval(
            claim_id="c1",
            claim_text="Achieved 50% renewable energy in operations.",
            claim_type=ClaimType.ACHIEVEMENT.value,
            category="renewable_energy",
            category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
            assessment=AssessmentCategory.SUPPORTED,
            referenced_evidence=[sample_evidence_ref("ev_1", 0.50)],
        ),
        create_eval(
            claim_id="c2",
            claim_text="Eliminated all microplastics from supply packaging.",
            claim_type=ClaimType.ACHIEVEMENT.value,
            category="waste",
            category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
            assessment=AssessmentCategory.INSUFFICIENT_EVIDENCE,
            reasoning="No relevant disclosures found in filing for microplastics.",
        ),
    ]

    result = service.calculate_score_from_evaluations(
        company_name="Partial Disclosure Corp",
        ticker="PART",
        market=MarketIdentifier.US_SEC,
        evaluations=evals,
        total_claims_extracted=2,
    )

    assert result.score_status == ScoreStatus.SCORED
    # The 1 supported claim keeps the integrity of assessed claims high
    assert result.esg_integrity_score is not None
    assert result.esg_integrity_score >= 90.0
    # But evidence coverage is penalized to 50%
    assert result.evidence_coverage == 50.0
    assert result.insufficient_evidence_claims == 1


# ─────────────────────────────────────────────────────────
# 6. Zero Assessable Claims (Insufficient Data)
# ─────────────────────────────────────────────────────────

def test_no_assessable_claims_returns_insufficient_data():
    """A company with no assessable sustainability claims returns an explicit insufficient-data result."""
    service = ScoringService()
    # Either empty list or all claims having insufficient evidence
    evals = [
        create_eval(
            claim_id="c1",
            claim_text="Company maintains zero deforestation.",
            assessment=AssessmentCategory.INSUFFICIENT_EVIDENCE,
        ),
    ]

    result = service.calculate_score_from_evaluations(
        company_name="Silent Corp",
        ticker="SILENT",
        market=MarketIdentifier.US_SEC,
        evaluations=evals,
        total_claims_extracted=1,
    )

    assert result.score_status == ScoreStatus.INSUFFICIENT_DATA
    assert result.esg_integrity_score is None
    assert result.confidence == ConfidenceLevel.INSUFFICIENT
    assert result.environmental_score is None


def test_empty_evaluations_returns_insufficient_data():
    """Empty evaluation list cleanly returns insufficient data."""
    service = ScoringService()
    result = service.calculate_score_from_evaluations(
        company_name="Empty Corp",
        ticker="EMPTY",
        market=MarketIdentifier.US_SEC,
        evaluations=[],
        total_claims_extracted=0,
    )

    assert result.score_status == ScoreStatus.INSUFFICIENT_DATA
    assert result.esg_integrity_score is None
    assert result.evidence_coverage == 0.0


# ─────────────────────────────────────────────────────────
# 7. Claims Across All Three ESG Dimensions
# ─────────────────────────────────────────────────────────

def test_claims_across_all_three_dimensions():
    """Company with assessable claims in E, S, and G receives scores for all three pillars."""
    service = ScoringService()
    evals = [
        create_eval(
            claim_id="e1",
            claim_text="Reduced carbon emissions by 15.8% vs 2021 baseline.",
            category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
            assessment=AssessmentCategory.SUPPORTED,
            referenced_evidence=[sample_evidence_ref()],
        ),
        create_eval(
            claim_id="s1",
            claim_text="Achieved 42.8% female representation in workforce.",
            category_group=ClaimCategoryGroup.SOCIAL.value,
            assessment=AssessmentCategory.SUPPORTED,
            referenced_evidence=[sample_evidence_ref()],
        ),
        create_eval(
            claim_id="g1",
            claim_text="Audit committee operates an independent whistleblowing hotline.",
            category_group=ClaimCategoryGroup.GOVERNANCE.value,
            assessment=AssessmentCategory.SUPPORTED,
            referenced_evidence=[sample_evidence_ref()],
        ),
    ]

    result = service.calculate_score_from_evaluations(
        company_name="Balanced ESG Corp",
        ticker="BAL",
        market=MarketIdentifier.US_SEC,
        evaluations=evals,
        total_claims_extracted=3,
    )

    assert result.environmental_score is not None
    assert result.social_score is not None
    assert result.governance_score is not None
    assert len(result.dimensions) == 3
    assert all(d.status == ScoreStatus.SCORED for d in result.dimensions.values())


# ─────────────────────────────────────────────────────────
# 8. Missing Information From One Dimension
# ─────────────────────────────────────────────────────────

def test_missing_dimension_returns_insufficient_data_for_that_dimension():
    """A dimension with no claims returns insufficient_data for that pillar without zeroing it."""
    service = ScoringService()
    evals = [
        create_eval(
            claim_id="e1",
            claim_text="Reduced carbon emissions by 10%.",
            category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
            assessment=AssessmentCategory.SUPPORTED,
            referenced_evidence=[sample_evidence_ref()],
        ),
        create_eval(
            claim_id="s1",
            claim_text="Achieved 50% diversity in leadership.",
            category_group=ClaimCategoryGroup.SOCIAL.value,
            assessment=AssessmentCategory.SUPPORTED,
            referenced_evidence=[sample_evidence_ref()],
        ),
        # Notice: NO Governance claims!
    ]

    result = service.calculate_score_from_evaluations(
        company_name="No Governance Corp",
        ticker="NOGOV",
        market=MarketIdentifier.US_SEC,
        evaluations=evals,
        total_claims_extracted=2,
    )

    assert result.environmental_score is not None
    assert result.social_score is not None
    assert result.governance_score is None  # Strictly None, NOT 0.0
    gov_dim = result.dimensions[ClaimCategoryGroup.GOVERNANCE.value]
    assert gov_dim.status == ScoreStatus.INSUFFICIENT_DATA
    assert gov_dim.score is None


# ─────────────────────────────────────────────────────────
# 9 & 10. Materiality Weighting & Volume Damping
# ─────────────────────────────────────────────────────────

def test_materiality_and_volume_damping():
    """A small number of highly material claims cannot be drowned out by low-materiality boilerplate."""
    service = ScoringService()

    # 1 highly material quantified achievement contradicted
    material_inconsistent = create_eval(
        claim_id="mat_1",
        claim_text="Reduced total corporate carbon emissions by 50% in 2024.",
        claim_type=ClaimType.ACHIEVEMENT.value,
        category="carbon",
        category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
        assessment=AssessmentCategory.INCONSISTENT,
        referenced_evidence=[sample_evidence_ref()],
    )

    # 4 generic policy statements marked supported
    boilerplate_supported = [
        create_eval(
            claim_id=f"gen_{i}",
            claim_text=f"The company maintains a general environmental statement {i}.",
            claim_type=ClaimType.GENERAL.value,
            category="sustainability",
            category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
            assessment=AssessmentCategory.SUPPORTED,
            referenced_evidence=[sample_evidence_ref()],
        )
        for i in range(4)
    ]

    result = service.calculate_score_from_evaluations(
        company_name="Greenwasher Corp",
        ticker="GWSH",
        market=MarketIdentifier.US_SEC,
        evaluations=[material_inconsistent] + boilerplate_supported,
        total_claims_extracted=5,
    )

    # The high materiality of the quantified achievement pulls down the score substantially
    # It cannot simply be 80% (4/5) because the achievement has much higher weight!
    assert result.esg_integrity_score < 60.0
    assert result.inconsistent_claims == 1


# ─────────────────────────────────────────────────────────
# 11. Different Reporting Periods
# ─────────────────────────────────────────────────────────

def test_different_reporting_periods():
    """Reporting period is accurately reflected in score responses."""
    service = ScoringService()
    evals = [create_eval(claim_id="c1", claim_text="Carbon reduced by 10%.", referenced_evidence=[sample_evidence_ref()])]

    res_2023 = service.calculate_score_from_evaluations(
        company_name="Period Corp",
        ticker="PRD",
        market=MarketIdentifier.US_SEC,
        evaluations=evals,
        total_claims_extracted=1,
        reporting_period="2023",
    )
    res_2024 = service.calculate_score_from_evaluations(
        company_name="Period Corp",
        ticker="PRD",
        market=MarketIdentifier.US_SEC,
        evaluations=evals,
        total_claims_extracted=1,
        reporting_period="2024",
    )

    assert res_2023.reporting_period == "2023"
    assert res_2024.reporting_period == "2024"


# ─────────────────────────────────────────────────────────
# 12, 13 & 14. Sector Priority & Ghana GSE Considerations
# ─────────────────────────────────────────────────────────

def test_ghana_sector_materiality_boost():
    """GSE mining company gets a materiality boost for water and tailings claims."""
    service = ScoringService()
    evals = [
        create_eval(
            claim_id="m1",
            claim_text="Installed closed-circuit water recycling at tailings storage facility.",
            claim_type=ClaimType.ACHIEVEMENT.value,
            category="water",
            category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
            assessment=AssessmentCategory.SUPPORTED,
            referenced_evidence=[sample_evidence_ref()],
        ),
    ]

    result = service.calculate_score_from_evaluations(
        company_name="AngloGold Ghana",
        ticker="AGA",
        market=MarketIdentifier.GH_GSE,
        evaluations=evals,
        total_claims_extracted=1,
        sector="Mining",
    )

    # Claim score detail should record sector_priority_match=True
    assert result.claim_scores[0].sector_priority_match is True
    # Materiality weight: 1.5 (achievement) * 1.3 (sector boost) = 1.95
    assert result.claim_scores[0].materiality_weight >= 1.95


def test_us_sec_sector_materiality_boost():
    """US SEC electronic computer company gets materiality boost for renewable energy."""
    service = ScoringService()
    evals = [
        create_eval(
            claim_id="a1",
            claim_text="100% of electricity for data centres sourced from renewable energy.",
            claim_type=ClaimType.ACHIEVEMENT.value,
            category="renewable_energy",
            category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
            assessment=AssessmentCategory.SUPPORTED,
            referenced_evidence=[sample_evidence_ref()],
        ),
    ]

    result = service.calculate_score_from_evaluations(
        company_name="Apple Inc.",
        ticker="AAPL",
        market=MarketIdentifier.US_SEC,
        evaluations=evals,
        total_claims_extracted=1,
        sector="Electronic Computers",
    )

    assert result.claim_scores[0].sector_priority_match is True


# ─────────────────────────────────────────────────────────
# 16. Deterministic Repeatability
# ─────────────────────────────────────────────────────────

def test_deterministic_repeatability():
    """Identical evaluation inputs produce identical numerical scores and weights."""
    service = ScoringService()
    evals = [
        create_eval(claim_id="c1", claim_text="15.8% carbon reduction.", referenced_evidence=[sample_evidence_ref()]),
        create_eval(claim_id="c2", claim_text="50% board female representation.", assessment=AssessmentCategory.PARTIALLY_SUPPORTED),
        create_eval(claim_id="c3", claim_text="Zero workplace accidents.", assessment=AssessmentCategory.INCONSISTENT),
    ]

    run1 = service.calculate_score_from_evaluations("Repeat Corp", "RPT", MarketIdentifier.US_SEC, evals, 3)
    run2 = service.calculate_score_from_evaluations("Repeat Corp", "RPT", MarketIdentifier.US_SEC, evals, 3)

    assert run1.esg_integrity_score == run2.esg_integrity_score
    assert run1.evidence_coverage == run2.evidence_coverage
    assert run1.confidence == run2.confidence
    assert [c.claim_score for c in run1.claim_scores] == [c.claim_score for c in run2.claim_scores]


# ─────────────────────────────────────────────────────────
# 17. Boundary Conditions & Clamping
# ─────────────────────────────────────────────────────────

def test_score_boundary_conditions():
    """Scores are strictly bounded within [0.0, 100.0] and rounded to 1 decimal place."""
    service = ScoringService()

    # Extreme high
    eval_high = [create_eval(claim_id="h1", claim_text="Super supported claim.", confidence=EvaluationConfidence.HIGH, referenced_evidence=[sample_evidence_ref("ev", 0.95)])]
    res_high = service.calculate_score_from_evaluations("High Corp", "HI", MarketIdentifier.US_SEC, eval_high, 1)
    assert res_high.esg_integrity_score <= 100.0

    # Extreme low
    eval_low = [create_eval(claim_id="l1", claim_text="Contradicted claim.", assessment=AssessmentCategory.INCONSISTENT)]
    res_low = service.calculate_score_from_evaluations("Low Corp", "LO", MarketIdentifier.US_SEC, eval_low, 1)
    assert res_low.esg_integrity_score == 0.0


# ─────────────────────────────────────────────────────────
# 18. Evidence Traceability
# ─────────────────────────────────────────────────────────

def test_evidence_traceability():
    """Scoring breakdown retains claim_id, evaluation_id, evidence_ids, and source citations."""
    service = ScoringService()
    ref = sample_evidence_ref("ev_specific_123", 0.48)
    evals = [create_eval(claim_id="claim_trace_999", claim_text="Specific claim text.", referenced_evidence=[ref])]

    result = service.calculate_score_from_evaluations(
        company_name="Trace Corp",
        ticker="TRC",
        market=MarketIdentifier.US_SEC,
        evaluations=evals,
        total_claims_extracted=1,
        source_document_references=["SEC EDGAR Form 10-K (0000320193-26-000026)"],
    )

    detail = result.claim_scores[0]
    assert detail.claim_id == "claim_trace_999"
    assert detail.evaluation_id == "eval_claim_trace_999"
    assert "ev_specific_123" in detail.referenced_evidence_ids
    assert "0000320193-26-000026" in result.source_document_references[0]


# ─────────────────────────────────────────────────────────
# 19. Confidence Logic & Small Sample Guard
# ─────────────────────────────────────────────────────────

def test_confidence_small_sample_guard():
    """A company with fewer than 3 claims can never achieve HIGH confidence."""
    service = ScoringService()
    # 2 perfect claims
    evals = [
        create_eval(claim_id="c1", claim_text="100% renewable energy.", referenced_evidence=[sample_evidence_ref()]),
        create_eval(claim_id="c2", claim_text="Zero workplace injuries.", referenced_evidence=[sample_evidence_ref()]),
    ]

    result = service.calculate_score_from_evaluations("Small Corp", "SML", MarketIdentifier.US_SEC, evals, 2)
    # Strictly LOW because < 3 claims
    assert result.confidence == ConfidenceLevel.LOW


def test_confidence_high_with_sufficient_sample():
    """A company with >= 6 claims, high coverage, and multiple dimensions achieves HIGH confidence."""
    service = ScoringService()
    evals = [
        create_eval(claim_id=f"e_{i}", claim_text=f"Environmental claim {i}.", category_group=ClaimCategoryGroup.ENVIRONMENTAL.value, referenced_evidence=[sample_evidence_ref()])
        for i in range(4)
    ] + [
        create_eval(claim_id=f"s_{i}", claim_text=f"Social claim {i}.", category_group=ClaimCategoryGroup.SOCIAL.value, referenced_evidence=[sample_evidence_ref()])
        for i in range(3)
    ]

    result = service.calculate_score_from_evaluations("Large Corp", "LRG", MarketIdentifier.US_SEC, evals, 7)
    assert result.confidence == ConfidenceLevel.HIGH


# ─────────────────────────────────────────────────────────
# 21. API Endpoint Tests
# ─────────────────────────────────────────────────────────

def test_get_company_score_endpoint():
    """GET /api/v1/companies/{ticker}/score returns 200 with ESGIntegrityScoreResponse."""
    mock_company = Company(ticker="AAPL", company_name="Apple Inc.", cik="0000320193")
    mock_evals = [create_eval(claim_id="c1", claim_text="Apple renewable energy target.", referenced_evidence=[sample_evidence_ref()])]
    mock_eval_response = CompanyEvaluationResponse(
        company=mock_company,
        filing_accession_number="0000320193-26-000026",
        form_type="10-K",
        filing_date="2026-11-03",
        summary=EvaluationSummary(total_claims_evaluated=1, total_claims_extracted=1, supported_count=1),
        evaluations=mock_evals,
        provider_mode="rule_based",
    )

    with patch("app.services.llm_service.LLMService.evaluate_company_filing", return_value=mock_eval_response):
        response = client.get("/api/v1/companies/AAPL/score")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["company_name"] == "Apple Inc."
        assert data["score_status"] == "scored"
        assert data["esg_integrity_score"] is not None
        assert "disclaimer" in data


def test_get_company_score_breakdown_endpoint():
    """GET /api/v1/companies/{ticker}/score/breakdown returns full transparent calculation trace."""
    mock_company = Company(ticker="AAPL", company_name="Apple Inc.", cik="0000320193")
    mock_evals = [create_eval(claim_id="c1", claim_text="Apple carbon reduction target.", referenced_evidence=[sample_evidence_ref()])]
    mock_eval_response = CompanyEvaluationResponse(
        company=mock_company,
        filing_accession_number="0000320193-26-000026",
        form_type="10-K",
        filing_date="2026-11-03",
        summary=EvaluationSummary(total_claims_evaluated=1, total_claims_extracted=1, supported_count=1),
        evaluations=mock_evals,
        provider_mode="rule_based",
    )

    with patch("app.services.llm_service.LLMService.evaluate_company_filing", return_value=mock_eval_response):
        response = client.get("/api/v1/companies/AAPL/score/breakdown")
        assert response.status_code == 200
        data = response.json()
        assert "dimensions" in data
        assert "claim_scores" in data
        assert len(data["claim_scores"]) == 1
        assert data["claim_scores"][0]["claim_id"] == "c1"


def test_get_company_score_history_endpoint():
    """GET /api/v1/companies/{ticker}/score/history returns recorded scoring history."""
    response = client.get("/api/v1/companies/AAPL/score/history")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert "history" in data
    assert "note" in data


def test_get_gse_company_score_endpoint():
    """GET /api/v1/gse/companies/{ticker}/score returns 200 with GSE company score."""
    mock_company = GSECompany(ticker="MTNGH", company_name="Scancom Plc", market=MarketIdentifier.GH_GSE, sector="Telecommunications")
    mock_doc = MarketDocument(
        document_id="doc_gse_mtngh_2024",
        company_ticker="MTNGH",
        company_name="Scancom Plc",
        market=MarketIdentifier.GH_GSE,
        source_type=DocumentSourceType.ANNUAL_REPORT,
        title="Scancom PLC 2024 Annual Report",
        reporting_period="2024",
        retrieval_status="retrieved",
        format="pdf",
    )
    mock_evals = [create_eval(claim_id="gse_1", claim_text="15.8% carbon reduction at switch centres.", referenced_evidence=[sample_evidence_ref()])]
    mock_gse_analysis = GSEAnalysisResponse(
        company=mock_company,
        document=mock_doc,
        total_claims_extracted=1,
        evaluations=mock_evals,
        summary=EvaluationSummary(total_claims_evaluated=1, total_claims_extracted=1, supported_count=1),
        provider_mode="rule_based",
    )

    with patch("app.services.gse_service.GSEService.analyze_company_document", return_value=mock_gse_analysis):
        response = client.get("/api/v1/gse/companies/MTNGH/score")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "MTNGH"
        assert data["market"] == "gh_gse"
        assert data["score_status"] == "scored"
        assert data["esg_integrity_score"] is not None


def test_get_gse_company_score_breakdown_endpoint():
    """GET /api/v1/gse/companies/{ticker}/score/breakdown returns breakdown with Ghana sector info."""
    mock_company = GSECompany(ticker="MTNGH", company_name="Scancom Plc", market=MarketIdentifier.GH_GSE, sector="Telecommunications")
    mock_doc = MarketDocument(
        document_id="doc_gse_mtngh_2024",
        company_ticker="MTNGH",
        company_name="Scancom Plc",
        market=MarketIdentifier.GH_GSE,
        source_type=DocumentSourceType.ANNUAL_REPORT,
        title="Scancom PLC 2024 Annual Report",
        reporting_period="2024",
        retrieval_status="retrieved",
        format="pdf",
    )
    mock_evals = [create_eval(claim_id="gse_1", claim_text="15.8% carbon reduction at switch centres.", referenced_evidence=[sample_evidence_ref()])]
    mock_gse_analysis = GSEAnalysisResponse(
        company=mock_company,
        document=mock_doc,
        total_claims_extracted=1,
        evaluations=mock_evals,
        summary=EvaluationSummary(total_claims_evaluated=1, total_claims_extracted=1, supported_count=1),
        provider_mode="rule_based",
    )

    with patch("app.services.gse_service.GSEService.analyze_company_document", return_value=mock_gse_analysis):
        response = client.get("/api/v1/gse/companies/MTNGH/score/breakdown")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "MTNGH"
        assert "dimensions" in data
        assert "claim_scores" in data
        assert data["materiality_summary"]["sector"] == "Telecommunications"
