"""Unit tests for Phase 6 LLMService and Consistency Evaluation Engine.

Tests:
- Every assessment category (supported, partially_supported, inconsistent, unsubstantiated, insufficient_evidence)
- Evidence ID validation & rejection of fabricated citations
- Empty evidence handling (insufficient_evidence)
- Contradictory evidence handling (inconsistent)
- Distinction between forward-looking targets and historical achievements
- Provider error handling & fallback
- Malformed LLM output handling
- In-memory evaluation caching
"""

import json
from unittest.mock import MagicMock, patch
import httpx
import pytest

from app.models.claim import Claim, ClaimCategoryGroup, ClaimType
from app.models.evaluation import (
    AssessmentCategory,
    EvaluationConfidence,
    EvaluationMode,
    EvidenceReference,
)
from app.models.evidence import Evidence, EvidenceRelationship, EvidenceStrength, EvidenceType
from app.models.filing import SECFiling
from app.services.llm_service import LLMService
from app.utils.config import Settings

MOCK_FILING = SECFiling(
    accession_number="0000320193-25-000079",
    form_type="10-K",
    filing_date="2025-10-31",
    report_date="2025-09-27",
    acceptance_date_time="2025-10-31T16:30:00.000Z",
    act="34",
    file_number="001-36743",
    film_number="251433890",
    items=["1", "1A", "7", "8"],
    size=12500000,
    is_xbrl=True,
    is_inline_xbrl=True,
    primary_document="aapl-20250927.htm",
    primary_doc_description="10-K",
    filing_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
)


def create_claim(
    claim_id: str = "cl_1",
    claim_text: str = "We target 100% renewable electricity by 2030.",
    claim_type: str = ClaimType.TARGET.value,
    category: str = "renewable_energy",
    target_value: str = "100%",
    metric: str = "renewable electricity",
) -> Claim:
    return Claim(
        claim_id=claim_id,
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text=claim_text,
        claim_type=claim_type,
        category=category,
        category_group=ClaimCategoryGroup.ENVIRONMENTAL.value,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        section_id="item_1",
        section_title="Item 1. Business",
        source_excerpt=claim_text,
        source_location="Item 1. Business",
        target_value=target_value,
        metric=metric,
        extraction_method="deterministic",
        confidence="high",
        status="active",
    )


def create_evidence(
    evidence_id: str,
    claim_id: str,
    text: str,
    relationship: str,
    section_id: str = "item_1",
    section_title: str = "Item 1. Business",
    relevance_score: float = 0.50,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        claim_id=claim_id,
        company_ticker="AAPL",
        company_name="Apple Inc.",
        evidence_text=text,
        evidence_type=EvidenceType.QUANTITATIVE.value,
        relationship=relationship,
        source_type="sec_10k",
        source_title="Apple Inc. 2025 Form 10-K",
        source_url=MOCK_FILING.filing_url,
        filing_accession_number=MOCK_FILING.accession_number,
        filing_date="2025-10-31",
        section_id=section_id,
        section_title=section_title,
        source_location=section_title,
        approximate_position=100,
        matched_concepts=["renewable energy"],
        matched_terms=["renewable", "electricity"],
        relevance_score=relevance_score,
        evidence_strength=EvidenceStrength.STRONG.value,
        extraction_method="deterministic",
        confidence="high",
    )


# 1. Insufficient Evidence when no evidence passages exist
def test_evaluation_insufficient_evidence_when_empty() -> None:
    service = LLMService(settings=Settings(OPENAI_API_KEY=None))
    claim = create_claim("cl_empty")

    evaluation = service.evaluate_claim(claim, [])
    assert evaluation.assessment == AssessmentCategory.INSUFFICIENT_EVIDENCE
    assert evaluation.confidence == EvaluationConfidence.HIGH
    assert evaluation.evaluation_mode == EvaluationMode.RULE_BASED
    assert len(evaluation.referenced_evidence) == 0
    assert "[Rule-Based Evaluation]" in evaluation.reasoning


# 2. Supported Target Claim
def test_evaluation_supported_target_claim() -> None:
    service = LLMService(settings=Settings(OPENAI_API_KEY=None))
    claim = create_claim("cl_target", claim_type=ClaimType.TARGET.value)
    ev = create_evidence(
        "ev_sup1",
        claim.claim_id,
        "The Company has committed to procuring 100% renewable electricity by 2030 across facilities.",
        relationship=EvidenceRelationship.SUPPORTING.value,
        relevance_score=0.60,
    )

    evaluation = service.evaluate_claim(claim, [ev])
    assert evaluation.assessment == AssessmentCategory.SUPPORTED
    assert evaluation.evaluation_mode == EvaluationMode.RULE_BASED
    assert len(evaluation.referenced_evidence) == 1
    assert evaluation.referenced_evidence[0].evidence_id == "ev_sup1"


# 3. Partially Supported Claim with Material Qualifying Evidence
def test_evaluation_partially_supported_with_qualifying_evidence() -> None:
    service = LLMService(settings=Settings(OPENAI_API_KEY=None))
    claim = create_claim("cl_part", claim_type=ClaimType.TARGET.value)
    ev_sup = create_evidence(
        "ev_sup",
        claim.claim_id,
        "The Company plans 100% renewable electricity by 2030.",
        relationship=EvidenceRelationship.SUPPORTING.value,
    )
    ev_qual = create_evidence(
        "ev_qual",
        claim.claim_id,
        "Initiatives are subject to grid availability and where feasible at selected facilities.",
        relationship=EvidenceRelationship.QUALIFYING.value,
    )

    evaluation = service.evaluate_claim(claim, [ev_sup, ev_qual])
    assert evaluation.assessment == AssessmentCategory.PARTIALLY_SUPPORTED
    assert evaluation.evaluation_mode == EvaluationMode.RULE_BASED
    assert len(evaluation.caveats) >= 1
    assert "subject to" in evaluation.caveats[0].lower() or "grid availability" in evaluation.caveats[0].lower()


# 4. Inconsistent Claim with Contradictory Evidence
def test_evaluation_inconsistent_contradictory_evidence() -> None:
    service = LLMService(settings=Settings(OPENAI_API_KEY=None))
    claim = create_claim(
        "cl_contra",
        claim_text="We achieved 100% renewable electricity in 2025.",
        claim_type=ClaimType.ACHIEVEMENT.value,
    )
    ev_contra = create_evidence(
        "ev_contra",
        claim.claim_id,
        "During fiscal 2025, the Company reached 45% renewable electricity with fossil fuels providing the rest.",
        relationship=EvidenceRelationship.CONTRADICTORY.value,
        section_id="item_7",
        section_title="Item 7. MD&A",
    )

    evaluation = service.evaluate_claim(claim, [ev_contra])
    assert evaluation.assessment == AssessmentCategory.INCONSISTENT
    assert evaluation.confidence == EvaluationConfidence.HIGH
    assert evaluation.evaluation_mode == EvaluationMode.RULE_BASED
    assert len(evaluation.referenced_evidence) == 1
    assert evaluation.referenced_evidence[0].evidence_id == "ev_contra"


# 5. Unsubstantiated Achievement Claim when Only Context or Targets Exist
def test_evaluation_unsubstantiated_achievement_without_proof() -> None:
    service = LLMService(settings=Settings(OPENAI_API_KEY=None))
    claim = create_claim(
        "cl_unsub",
        claim_text="We achieved net-zero emissions across all product lifecycles in 2025.",
        claim_type=ClaimType.ACHIEVEMENT.value,
    )
    # Evidence only mentions future plans or general operational context, not verified realization
    ev_context = create_evidence(
        "ev_ctx",
        claim.claim_id,
        "The Company continues to explore energy efficiency programs across manufacturing operations.",
        relationship=EvidenceRelationship.CONTEXTUAL.value,
    )

    evaluation = service.evaluate_claim(claim, [ev_context])
    # Must be UNSUBSTANTIATED, distinct from INSUFFICIENT_EVIDENCE
    assert evaluation.assessment == AssessmentCategory.UNSUBSTANTIATED
    assert evaluation.assessment != AssessmentCategory.INSUFFICIENT_EVIDENCE
    assert evaluation.evaluation_mode == EvaluationMode.RULE_BASED
    assert "lacks measurable achievement" in evaluation.caveats[0].lower()


# 6. Target Language Cannot Prove Historical Achievement Realization
def test_target_language_does_not_prove_achievement() -> None:
    service = LLMService(settings=Settings(OPENAI_API_KEY=None))
    claim = create_claim(
        "cl_ach_target_check",
        claim_text="We achieved 100% recycled cobalt in all batteries in 2025.",
        claim_type=ClaimType.ACHIEVEMENT.value,
    )
    ev_target_lang = create_evidence(
        "ev_tgt",
        claim.claim_id,
        "We aim to transition to 100% recycled cobalt in all Apple-designed batteries by 2025.",
        relationship=EvidenceRelationship.CONTEXTUAL.value,  # Contextual because it's a target, not an achievement
    )

    evaluation = service.evaluate_claim(claim, [ev_target_lang])
    assert evaluation.assessment != AssessmentCategory.SUPPORTED
    assert evaluation.assessment == AssessmentCategory.UNSUBSTANTIATED


# 7. Evidence ID Validation: Valid IDs Accepted, Fabricated IDs Rejected
def test_validate_and_build_references_rejects_fabricated_ids() -> None:
    claim = create_claim("cl_val")
    ev1 = create_evidence("ev_real_1", claim.claim_id, "Real evidence text 1", EvidenceRelationship.SUPPORTING.value)
    ev2 = create_evidence("ev_real_2", claim.claim_id, "Real evidence text 2", EvidenceRelationship.QUALIFYING.value)
    ev_map = {"ev_real_1": ev1, "ev_real_2": ev2}

    raw_ids = ["ev_real_1", "ev_fake_999", "ev_real_2", "ev_hallucinated"]
    valid_refs, rejected_ids = LLMService.validate_and_build_references(raw_ids, ev_map)

    assert len(valid_refs) == 2
    assert [r.evidence_id for r in valid_refs] == ["ev_real_1", "ev_real_2"]
    assert rejected_ids == ["ev_fake_999", "ev_hallucinated"]


# 8. Live LLM Mode with Successful Structured Output
def test_evaluate_claim_with_mock_llm_success() -> None:
    claim = create_claim("cl_mock_llm")
    ev = create_evidence(
        "ev_123",
        claim.claim_id,
        "We have achieved 100% renewable electricity across all corporate facilities.",
        relationship=EvidenceRelationship.SUPPORTING.value,
    )

    mock_llm_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "assessment": "supported",
                        "confidence": "high",
                        "reasoning": "The corporate filing confirms 100% renewable electricity in corporate facilities.",
                        "caveats": [],
                        "referenced_evidence_ids": ["ev_123"],
                    })
                }
            }
        ]
    }

    mock_client = MagicMock(spec=httpx.Client)
    mock_post_resp = MagicMock()
    mock_post_resp.json.return_value = mock_llm_response
    mock_post_resp.raise_for_status.return_value = None
    mock_client.post.return_value = mock_post_resp

    service = LLMService(
        settings=Settings(OPENAI_API_KEY="sk-test-fake-key", LLM_MODEL="gpt-4o"),
        http_client=mock_client,
    )

    assert service.is_live_llm_available is True
    assert service.active_provider_mode == "llm"

    evaluation = service.evaluate_claim(claim, [ev])
    assert evaluation.assessment == AssessmentCategory.SUPPORTED
    assert evaluation.confidence == EvaluationConfidence.HIGH
    assert evaluation.evaluation_mode == EvaluationMode.LLM
    assert evaluation.model_name == "gpt-4o"
    assert len(evaluation.referenced_evidence) == 1
    assert evaluation.referenced_evidence[0].evidence_id == "ev_123"


# 9. Unsupported Citations (All Fabricated IDs) Triggers Safe Fallback
def test_llm_all_fabricated_ids_falls_back_to_rule_based() -> None:
    claim = create_claim("cl_fab", claim_type=ClaimType.TARGET.value)
    ev = create_evidence(
        "ev_real",
        claim.claim_id,
        "The Company has committed to 100% renewable electricity by 2030.",
        relationship=EvidenceRelationship.SUPPORTING.value,
    )

    # LLM claims supported but returns completely fake evidence IDs
    mock_llm_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "assessment": "supported",
                        "confidence": "high",
                        "reasoning": "Claim is supported based on outside news.",
                        "caveats": [],
                        "referenced_evidence_ids": ["ev_completely_invented"],
                    })
                }
            }
        ]
    }

    mock_client = MagicMock(spec=httpx.Client)
    mock_post_resp = MagicMock()
    mock_post_resp.json.return_value = mock_llm_response
    mock_post_resp.raise_for_status.return_value = None
    mock_client.post.return_value = mock_post_resp

    service = LLMService(
        settings=Settings(OPENAI_API_KEY="sk-test-fake-key"),
        http_client=mock_client,
    )

    evaluation = service.evaluate_claim(claim, [ev])
    # Must reject fabricated ID and fall back safely to rule-based evaluation
    assert evaluation.evaluation_mode == EvaluationMode.RULE_BASED
    assert evaluation.referenced_evidence[0].evidence_id == "ev_real"


# 10. Provider HTTP Error or Timeout Graceful Fallback
def test_llm_provider_error_graceful_fallback() -> None:
    claim = create_claim("cl_err")
    ev = create_evidence(
        "ev_real_err",
        claim.claim_id,
        "The Company commits to 100% renewable electricity by 2030.",
        relationship=EvidenceRelationship.SUPPORTING.value,
    )

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.side_effect = httpx.ConnectTimeout("Connection to OpenAI timed out")

    service = LLMService(
        settings=Settings(OPENAI_API_KEY="sk-test-fake-key"),
        http_client=mock_client,
    )

    evaluation = service.evaluate_claim(claim, [ev])
    assert evaluation.evaluation_mode == EvaluationMode.RULE_BASED
    assert "Switched to rule-based evaluation due to provider error" in evaluation.reasoning


# 11. Malformed JSON from Provider Graceful Fallback
def test_llm_malformed_json_graceful_fallback() -> None:
    claim = create_claim("cl_malformed")
    ev = create_evidence(
        "ev_real_mal",
        claim.claim_id,
        "The Company commits to 100% renewable electricity by 2030.",
        relationship=EvidenceRelationship.SUPPORTING.value,
    )

    mock_llm_response = {
        "choices": [
            {
                "message": {
                    "content": "This is not JSON text! Error 500."
                }
            }
        ]
    }

    mock_client = MagicMock(spec=httpx.Client)
    mock_post_resp = MagicMock()
    mock_post_resp.json.return_value = mock_llm_response
    mock_post_resp.raise_for_status.return_value = None
    mock_client.post.return_value = mock_post_resp

    service = LLMService(
        settings=Settings(OPENAI_API_KEY="sk-test-fake-key"),
        http_client=mock_client,
    )

    evaluation = service.evaluate_claim(claim, [ev])
    assert evaluation.evaluation_mode == EvaluationMode.RULE_BASED


# 12. In-Memory Evaluation Caching
def test_evaluation_caching_and_clear_cache() -> None:
    service = LLMService(settings=Settings(OPENAI_API_KEY=None))
    claim = create_claim("cl_cache")
    ev = create_evidence("ev_c", claim.claim_id, "Support text", EvidenceRelationship.SUPPORTING.value)
    eval_res = service.evaluate_claim(claim, [ev])
    summary = service._compute_summary([eval_res])

    service._evaluation_cache[MOCK_FILING.accession_number] = (summary, [eval_res])
    assert MOCK_FILING.accession_number in service._evaluation_cache

    service.clear_cache()
    assert len(service._evaluation_cache) == 0


# 13. Sustainability Relevance and Exclusion Filtering
def test_is_sustainability_claim_exclusion() -> None:
    # 1. Litigation defense statement must be excluded
    lit_claim = create_claim(
        "cl_lit",
        claim_text="The Company believes it has substantial defenses and intends to vigorously defend itself.",
        claim_type=ClaimType.TARGET.value,
        category="compliance",
    )
    is_valid, reason = LLMService.is_sustainability_claim(lit_claim)
    assert not is_valid
    assert reason == "litigation_defense"

    # 2. Dividend increase statement must be excluded
    div_claim = create_claim(
        "cl_div",
        claim_text="The Company intends to increase its dividend on an annual basis, subject to declaration by the Board.",
        claim_type=ClaimType.TARGET.value,
        category="compliance",
    )
    is_valid, reason = LLMService.is_sustainability_claim(div_claim)
    assert not is_valid
    assert reason == "capital_allocation"

    # 3. Revenue delivery accounting statement must be excluded
    rev_claim = create_claim(
        "cl_rev",
        claim_text="For the Company’s Services net sales, control transfers over time as services are delivered.",
        claim_type=ClaimType.ACHIEVEMENT.value,
        category="compliance",
    )
    is_valid, reason = LLMService.is_sustainability_claim(rev_claim)
    assert not is_valid
    assert reason == "financial_accounting"

    # 4. Genuine sustainability target must be accepted
    esg_claim = create_claim(
        "cl_esg",
        claim_text="We target a 50% reduction in greenhouse gas emissions by 2030.",
        claim_type=ClaimType.TARGET.value,
        category="greenhouse_gas",
    )
    is_valid, reason = LLMService.is_sustainability_claim(esg_claim)
    assert is_valid
    assert reason is None


# 14. Policy vs Performance Outcome Differentiation
def test_policy_vs_performance_differentiation_reasoning() -> None:
    service = LLMService(settings=Settings(OPENAI_API_KEY=None))
    policy_claim = Claim(
        claim_id="cl_policy_1",
        company_ticker="AAPL",
        company_name="Apple Inc.",
        claim_text="The Company is an equal opportunity employer committed to inclusion and to providing a workplace free of harassment or discrimination.",
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
        source_excerpt="The Company is an equal opportunity employer committed to inclusion.",
        source_location="Item 1. Business",
    )
    supporting_ev = create_evidence(
        "ev_pol_sup",
        policy_claim.claim_id,
        "The Company is an equal opportunity employer committed to inclusion and to providing a workplace free of harassment or discrimination.",
        relationship=EvidenceRelationship.SUPPORTING.value,
        section_id="item_1",
        section_title="Item 1. Business",
    )

    evaluation = service.evaluate_claim(policy_claim, [supporting_ev])

    assert evaluation.assessment == AssessmentCategory.SUPPORTED
    # Must explicitly state policy commitment is affirmed
    assert "inclusion policy commitment is affirmed" in evaluation.reasoning
    # Must explicitly note that policy does not establish quantitative outcome metrics
    assert "filing does not report quantitative performance or representation outcome metrics" in evaluation.reasoning
    # Caveat must be present
    assert any("lacks quantitative workforce representation" in c for c in evaluation.caveats)


# 15. Summary Count Tracking with Excluded Claims
def test_evaluation_summary_count_integrity() -> None:
    service = LLMService(settings=Settings(OPENAI_API_KEY=None))
    claim = create_claim("cl_sum")
    ev = create_evidence("ev_sum", claim.claim_id, "Support text", EvidenceRelationship.SUPPORTING.value)
    evaluation = service.evaluate_claim(claim, [ev])

    summary = service._compute_summary(
        evaluations=[evaluation],
        total_claims_extracted=5,
        excluded_claims_count=4,
    )

    assert summary.total_claims_evaluated == 1
    assert summary.total_claims_extracted == 5
    assert summary.excluded_claims_count == 4
    assert summary.supported_count == 1
    assert summary.total_claims_evaluated + summary.excluded_claims_count == summary.total_claims_extracted
