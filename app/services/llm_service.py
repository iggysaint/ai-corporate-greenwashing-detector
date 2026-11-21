"""LLM-Assisted Evidence Evaluation & Consistency Verification Service.

Responsible for evaluating extracted sustainability claims against retrieved SEC
10-K evidence records. Supports both live LLM-powered evaluation (via OpenAI API)
and a deterministic rule-based fallback mode for offline, testing, and CI/CD environments.

All evaluations are objective, analytical research assessments grounded strictly in
supplied filing disclosures. This service does NOT make legal accusations of fraud or
greenwashing.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.models.claim import Claim, ClaimCategoryGroup, ClaimType
from app.models.company import Company
from app.models.evaluation import (
    AssessmentCategory,
    ClaimEvaluation,
    CompanyEvaluationResponse,
    EvaluationConfidence,
    EvaluationMode,
    EvaluationSummary,
    EvidenceReference,
    LLMRawAssessment,
    SingleClaimEvaluationResponse,
)
from app.models.evidence import ClaimEvidenceResult, Evidence, EvidenceRelationship
from app.models.filing import SECFiling
from app.services.claims_service import ClaimsService, get_claims_service
from app.services.document_service import DocumentService, get_document_service
from app.services.evidence_service import EvidenceService, get_evidence_service
from app.services.sec_service import SECService, get_sec_service, normalize_and_validate_ticker
from app.utils.config import Settings, get_settings
from app.utils.exceptions import (
    ClaimNotFoundError,
    EvaluationNotFoundError,
    FilingNotFoundError,
    LLMOutputValidationError,
    LLMProviderError,
    LLMServiceError,
)

logger = logging.getLogger(__name__)

SYSTEM_EVALUATION_PROMPT = """You are a neutral analytical research assistant evaluating corporate sustainability claims against SEC 10-K filing disclosures.

Rules:
1. Base your assessment ONLY on the supplied claim and the provided evidence passages. Do NOT use outside knowledge, news, or assumptions not found in the evidence.
2. Select exactly ONE assessment category from:
   - "supported": The claim's commitments or achievements are directly corroborated by affirmative disclosures without unresolved material caveats.
   - "partially_supported": Disclosures corroborate parts of the claim, but highlight material caveats, limitations, exclusions, or interim milestones.
   - "inconsistent": Disclosed SEC metrics, timelines, or factual statements contradict the claim.
   - "unsubstantiated": Relevant disclosure context exists in the filing, but provides inadequate substantiation, metrics, or verification for the affirmative assertions in the claim.
   - "insufficient_evidence": No relevant evidence passages exist in the filing for the claim.
3. Distinguish forward-looking commitments from achieved outcomes: a company's general sustainability goal or target does NOT prove that a specific historical milestone was achieved.
4. Reference ONLY evidence_ids provided in the supplied evidence list. Do NOT invent evidence IDs, numbers, or quotes.
5. Do NOT make accusations of fraud, illegal conduct, or "greenwashing". Maintain an objective, balanced, and evidence-grounded research tone.
6. Provide your output strictly as a JSON object with this structure:
{
  "assessment": "supported" | "partially_supported" | "inconsistent" | "unsubstantiated" | "insufficient_evidence",
  "confidence": "high" | "medium" | "low",
  "reasoning": "Clear, objective explanation referencing the evidence",
  "caveats": ["specific limitation or qualification 1", "specific limitation or qualification 2"],
  "referenced_evidence_ids": ["ev_id_1", "ev_id_2"]
}"""


# Patterns indicating non-sustainability claims (ordinary legal proceedings, dividends, accounting)
NON_SUSTAINABILITY_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Litigation defense / legal proceedings
    (
        re.compile(
            r"\b(?:substantial\s+defenses|vigorously\s+defend|injunction|legal\s+proceedings|antitrust|district\s+court|lawsuit|litigation|court\s+of\s+appeals)\b",
            re.I,
        ),
        "litigation_defense",
    ),
    # Financial / Capital allocation / Dividends
    (
        re.compile(
            r"\b(?:dividend|repurchase\s+of\s+shares|share\s+repurchase|capital\s+return|capital\s+allocation)\b",
            re.I,
        ),
        "capital_allocation",
    ),
    # Financial accounting / software capitalization / revenue recognition / tax disputes
    (
        re.compile(
            r"\b(?:asu\s+\d+|capitalization\s+of\s+software|software\s+costs|performance\s+obligation|sales\s+price|revenue\s+allocated|net\s+sales|tax\s+opinions|state\s+aid)\b",
            re.I,
        ),
        "financial_accounting",
    ),
]


class LLMService:
    """Service for evaluating claim-evidence consistency using LLM or rule-based fallback."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        sec_service: Optional[SECService] = None,
        doc_service: Optional[DocumentService] = None,
        claims_service: Optional[ClaimsService] = None,
        evidence_service: Optional[EvidenceService] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sec_service = sec_service or get_sec_service()
        self.doc_service = doc_service or get_document_service()
        self.claims_service = claims_service or get_claims_service()
        self.evidence_service = evidence_service or get_evidence_service()

        self._custom_client = http_client is not None
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(self.settings.LLM_TIMEOUT, connect=10.0),
            headers={"Content-Type": "application/json"},
        )

        # In-memory evaluation cache keyed by filing accession number: accession -> (summary, evaluations)
        self._evaluation_cache: Dict[str, Tuple[EvaluationSummary, List[ClaimEvaluation]]] = {}

    def close(self) -> None:
        """Close the HTTP client if owned by this instance."""
        if not self._custom_client and self._client:
            self._client.close()

    def __enter__(self) -> "LLMService":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def clear_cache(self) -> None:
        """Clear the in-memory evaluation cache."""
        self._evaluation_cache.clear()

    @property
    def is_live_llm_available(self) -> bool:
        """Return True if a valid live LLM API key is configured."""
        return bool(self.settings.OPENAI_API_KEY and self.settings.OPENAI_API_KEY.strip())

    @property
    def active_provider_mode(self) -> str:
        """Return the current active provider mode ('llm' or 'rule_based')."""
        return EvaluationMode.LLM.value if self.is_live_llm_available else EvaluationMode.RULE_BASED.value

    @staticmethod
    def is_sustainability_claim(claim: Claim) -> Tuple[bool, Optional[str]]:
        """Verify whether an extracted claim is genuinely sustainability/ESG-related.

        Returns (True, None) if valid, or (False, reason) if it represents
        ordinary legal proceedings, dividend policy, routine financial accounting,
        or non-ESG disclosures.
        """
        for pattern, reason in NON_SUSTAINABILITY_PATTERNS:
            if pattern.search(claim.claim_text):
                return False, reason

        # Verify category group is a recognized ESG pillar
        if claim.category_group not in (
            ClaimCategoryGroup.ENVIRONMENTAL,
            ClaimCategoryGroup.SOCIAL,
            ClaimCategoryGroup.GOVERNANCE,
            ClaimCategoryGroup.ENVIRONMENTAL.value,
            ClaimCategoryGroup.SOCIAL.value,
            ClaimCategoryGroup.GOVERNANCE.value,
        ):
            return False, "non_esg_category_group"

        return True, None

    # ─────────────────────────────────────────────────────────
    # ID Generation & Citation Validation
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def generate_evaluation_id(claim_id: str, mode: str) -> str:
        """Generate a deterministic, traceable evaluation ID."""
        digest = hashlib.sha256(f"{claim_id}_{mode}".encode("utf-8")).hexdigest()[:12]
        return f"eval_{digest}"

    @staticmethod
    def validate_and_build_references(
        raw_ids: List[str],
        evidence_map: Dict[str, Evidence],
    ) -> Tuple[List[EvidenceReference], List[str]]:
        """Validate referenced evidence IDs against supplied evidence and build citations.

        Returns:
            Tuple of (valid_references, rejected_fabricated_ids).
        """
        valid_refs: List[EvidenceReference] = []
        rejected_ids: List[str] = []

        for ev_id in raw_ids:
            clean_id = ev_id.strip()
            if clean_id in evidence_map:
                ev = evidence_map[clean_id]
                valid_refs.append(
                    EvidenceReference(
                        evidence_id=ev.evidence_id,
                        section_id=ev.section_id,
                        relevance_score=ev.relevance_score,
                        relationship=ev.relationship,
                        quote=ev.evidence_text[:300],
                    )
                )
            else:
                logger.warning("Rejecting fabricated or unsupplied evidence ID from LLM: %s", clean_id)
                rejected_ids.append(clean_id)

        return valid_refs, rejected_ids

    # ─────────────────────────────────────────────────────────
    # Deterministic Rule-Based Fallback Synthesizer
    # ─────────────────────────────────────────────────────────

    def evaluate_claim_rule_based(
        self,
        claim: Claim,
        evidence_list: List[Evidence],
    ) -> ClaimEvaluation:
        """Perform a conservative, deterministic rule-based evaluation of a claim.

        Explicitly marked with evaluation_mode='rule_based'. Adheres to conservative
        principles:
        - INSUFFICIENT_EVIDENCE when no relevant evidence was found.
        - UNSUBSTANTIATED when context exists but affirmative proof/metrics are absent.
        - PARTIALLY_SUPPORTED when material caveats or conditions exist.
        - INCONSISTENT when conflicting data exists.
        - SUPPORTED only when unhedged corroboration is found.
        """
        eval_id = self.generate_evaluation_id(claim.claim_id, EvaluationMode.RULE_BASED.value)

        # 1. Zero evidence found -> INSUFFICIENT_EVIDENCE
        if not evidence_list:
            return ClaimEvaluation(
                evaluation_id=eval_id,
                claim_id=claim.claim_id,
                company_ticker=claim.company_ticker,
                company_name=claim.company_name,
                claim_text=claim.claim_text,
                claim_type=claim.claim_type,
                category=claim.category,
                category_group=claim.category_group,
                assessment=AssessmentCategory.INSUFFICIENT_EVIDENCE,
                confidence=EvaluationConfidence.HIGH,
                reasoning=(
                    "[Rule-Based Evaluation] No relevant evidence passages were identified in the filing "
                    "to substantiate or evaluate this claim."
                ),
                caveats=["No matching disclosures found in filing."],
                referenced_evidence=[],
                evaluation_mode=EvaluationMode.RULE_BASED,
                model_name=None,
            )

        evidence_map = {e.evidence_id: e for e in evidence_list}

        # 2. Contradictory evidence detected -> INCONSISTENT
        contradictory_items = [e for e in evidence_list if e.relationship == EvidenceRelationship.CONTRADICTORY.value]
        if contradictory_items:
            top_contra = contradictory_items[0]
            ref = EvidenceReference(
                evidence_id=top_contra.evidence_id,
                section_id=top_contra.section_id,
                relevance_score=top_contra.relevance_score,
                relationship=top_contra.relationship,
                quote=top_contra.evidence_text[:300],
            )
            return ClaimEvaluation(
                evaluation_id=eval_id,
                claim_id=claim.claim_id,
                company_ticker=claim.company_ticker,
                company_name=claim.company_name,
                claim_text=claim.claim_text,
                claim_type=claim.claim_type,
                category=claim.category,
                category_group=claim.category_group,
                assessment=AssessmentCategory.INCONSISTENT,
                confidence=EvaluationConfidence.HIGH,
                reasoning=(
                    f"[Rule-Based Evaluation] SEC filing disclosures report conflicting data regarding this claim "
                    f"in section {top_contra.section_title}. The disclosed figures or statements indicate a material divergence."
                ),
                caveats=["Conflicting disclosure identified in filing."],
                referenced_evidence=[ref],
                evaluation_mode=EvaluationMode.RULE_BASED,
                model_name=None,
            )

        supporting_items = [e for e in evidence_list if e.relationship == EvidenceRelationship.SUPPORTING.value]
        qualifying_items = [e for e in evidence_list if e.relationship == EvidenceRelationship.QUALIFYING.value]
        contextual_items = [e for e in evidence_list if e.relationship == EvidenceRelationship.CONTEXTUAL.value]

        cat_str = claim.category.replace("_", " ")

        # 3. Claims claiming realization of past achievement or current performance
        if claim.claim_type in (ClaimType.ACHIEVEMENT.value, ClaimType.CURRENT_STATE.value):
            if supporting_items:
                top_sup = supporting_items[0]
                refs = [
                    EvidenceReference(
                        evidence_id=e.evidence_id,
                        section_id=e.section_id,
                        relevance_score=e.relevance_score,
                        relationship=e.relationship,
                        quote=e.evidence_text[:300],
                    )
                    for e in supporting_items[:2]
                ]

                if qualifying_items:
                    caveat_text = qualifying_items[0].evidence_text[:180]
                    return ClaimEvaluation(
                        evaluation_id=eval_id,
                        claim_id=claim.claim_id,
                        company_ticker=claim.company_ticker,
                        company_name=claim.company_name,
                        claim_text=claim.claim_text,
                        claim_type=claim.claim_type,
                        category=claim.category,
                        category_group=claim.category_group,
                        assessment=AssessmentCategory.PARTIALLY_SUPPORTED,
                        confidence=EvaluationConfidence.MEDIUM,
                        reasoning=(
                            f"[Rule-Based Evaluation] Disclosed SEC data corroborates the reported {cat_str} achievement "
                            f"in {top_sup.section_title}, but accompanying disclosures specify operational qualifications, scope limitations, or caveats."
                        ),
                        caveats=[f"Filing specifies scope qualification: {caveat_text}"],
                        referenced_evidence=refs,
                        evaluation_mode=EvaluationMode.RULE_BASED,
                        model_name=None,
                    )
                else:
                    return ClaimEvaluation(
                        evaluation_id=eval_id,
                        claim_id=claim.claim_id,
                        company_ticker=claim.company_ticker,
                        company_name=claim.company_name,
                        claim_text=claim.claim_text,
                        claim_type=claim.claim_type,
                        category=claim.category,
                        category_group=claim.category_group,
                        assessment=AssessmentCategory.SUPPORTED,
                        confidence=EvaluationConfidence.HIGH if top_sup.relevance_score >= 0.50 else EvaluationConfidence.MEDIUM,
                        reasoning=(
                            f"[Rule-Based Evaluation] The reported {cat_str} achievement is corroborated by affirmative disclosures "
                            f"and quantitative or performance data in {top_sup.section_title}."
                        ),
                        caveats=[],
                        referenced_evidence=refs,
                        evaluation_mode=EvaluationMode.RULE_BASED,
                        model_name=None,
                    )
            else:
                # No supporting achievement evidence exists, only forward-looking targets or general context
                # Rule: Target language cannot prove an achievement -> UNSUBSTANTIATED
                refs = [
                    EvidenceReference(
                        evidence_id=e.evidence_id,
                        section_id=e.section_id,
                        relevance_score=e.relevance_score,
                        relationship=e.relationship,
                        quote=e.evidence_text[:300],
                    )
                    for e in (contextual_items or qualifying_items)[:1]
                ]
                return ClaimEvaluation(
                    evaluation_id=eval_id,
                    claim_id=claim.claim_id,
                    company_ticker=claim.company_ticker,
                    company_name=claim.company_name,
                    claim_text=claim.claim_text,
                    claim_type=claim.claim_type,
                    category=claim.category,
                    category_group=claim.category_group,
                    assessment=AssessmentCategory.UNSUBSTANTIATED,
                    confidence=EvaluationConfidence.HIGH,
                    reasoning=(
                        f"[Rule-Based Evaluation] While the filing addresses {cat_str} in related contexts, "
                        f"it provides no verifiable performance metrics or completed milestones substantiating "
                        f"that this specific achievement was realized."
                    ),
                    caveats=[f"Filing lacks measurable achievement or progress metrics for {cat_str}."],
                    referenced_evidence=refs,
                    evaluation_mode=EvaluationMode.RULE_BASED,
                    model_name=None,
                )

        # 4. Target claims (forward-looking commitments)
        if claim.claim_type == ClaimType.TARGET.value:
            if supporting_items:
                top_sup = supporting_items[0]
                refs = [
                    EvidenceReference(
                        evidence_id=e.evidence_id,
                        section_id=e.section_id,
                        relevance_score=e.relevance_score,
                        relationship=e.relationship,
                        quote=e.evidence_text[:300],
                    )
                    for e in supporting_items[:2]
                ]

                if qualifying_items:
                    caveat_text = qualifying_items[0].evidence_text[:180]
                    return ClaimEvaluation(
                        evaluation_id=eval_id,
                        claim_id=claim.claim_id,
                        company_ticker=claim.company_ticker,
                        company_name=claim.company_name,
                        claim_text=claim.claim_text,
                        claim_type=claim.claim_type,
                        category=claim.category,
                        category_group=claim.category_group,
                        assessment=AssessmentCategory.PARTIALLY_SUPPORTED,
                        confidence=EvaluationConfidence.MEDIUM,
                        reasoning=(
                            f"[Rule-Based Evaluation] The company's forward-looking {cat_str} commitment is affirmed in {top_sup.section_title}, "
                            f"but disclosures disclose explicit operational contingencies, scope boundaries, or feasibility conditions."
                        ),
                        caveats=[f"Target subject to disclosed condition: {caveat_text}"],
                        referenced_evidence=refs,
                        evaluation_mode=EvaluationMode.RULE_BASED,
                        model_name=None,
                    )
                else:
                    return ClaimEvaluation(
                        evaluation_id=eval_id,
                        claim_id=claim.claim_id,
                        company_ticker=claim.company_ticker,
                        company_name=claim.company_name,
                        claim_text=claim.claim_text,
                        claim_type=claim.claim_type,
                        category=claim.category,
                        category_group=claim.category_group,
                        assessment=AssessmentCategory.SUPPORTED,
                        confidence=EvaluationConfidence.MEDIUM,
                        reasoning=(
                            f"[Rule-Based Evaluation] The forward-looking {cat_str} commitment is formally acknowledged "
                            f"and affirmed in the company's regulatory filing disclosures in {top_sup.section_title}."
                        ),
                        caveats=[],
                        referenced_evidence=refs,
                        evaluation_mode=EvaluationMode.RULE_BASED,
                        model_name=None,
                    )
            else:
                refs = [
                    EvidenceReference(
                        evidence_id=e.evidence_id,
                        section_id=e.section_id,
                        relevance_score=e.relevance_score,
                        relationship=e.relationship,
                        quote=e.evidence_text[:300],
                    )
                    for e in (contextual_items or qualifying_items)[:1]
                ]
                return ClaimEvaluation(
                    evaluation_id=eval_id,
                    claim_id=claim.claim_id,
                    company_ticker=claim.company_ticker,
                    company_name=claim.company_name,
                    claim_text=claim.claim_text,
                    claim_type=claim.claim_type,
                    category=claim.category,
                    category_group=claim.category_group,
                    assessment=AssessmentCategory.UNSUBSTANTIATED,
                    confidence=EvaluationConfidence.MEDIUM,
                    reasoning=(
                        f"[Rule-Based Evaluation] The claim states a forward-looking {cat_str} commitment, but the filing disclosures "
                        f"provide no formal target milestones, implementation details, or roadmaps."
                    ),
                    caveats=[f"Filing contains no formal commitment or milestone targets for {cat_str}."],
                    referenced_evidence=refs,
                    evaluation_mode=EvaluationMode.RULE_BASED,
                    model_name=None,
                )

        # 5. Policy claims (Code of Conduct, Governance standards, Equal Opportunity)
        if claim.claim_type == ClaimType.POLICY.value:
            if supporting_items:
                top_sup = supporting_items[0]
                refs = [
                    EvidenceReference(
                        evidence_id=e.evidence_id,
                        section_id=e.section_id,
                        relevance_score=e.relevance_score,
                        relationship=e.relationship,
                        quote=e.evidence_text[:300],
                    )
                    for e in supporting_items[:2]
                ]
                if qualifying_items:
                    caveat_text = qualifying_items[0].evidence_text[:180]
                    return ClaimEvaluation(
                        evaluation_id=eval_id,
                        claim_id=claim.claim_id,
                        company_ticker=claim.company_ticker,
                        company_name=claim.company_name,
                        claim_text=claim.claim_text,
                        claim_type=claim.claim_type,
                        category=claim.category,
                        category_group=claim.category_group,
                        assessment=AssessmentCategory.PARTIALLY_SUPPORTED,
                        confidence=EvaluationConfidence.MEDIUM,
                        reasoning=(
                            f"[Rule-Based Evaluation] The company's {cat_str} policy framework is active in {top_sup.section_title}, "
                            f"but filing disclosures cite compliance exceptions, operational violations, or enforcement challenges."
                        ),
                        caveats=[
                            f"Filing notes policy compliance challenges: {caveat_text}",
                            "Documented policy confirms corporate framework, but does not establish quantitative outcome metrics.",
                        ],
                        referenced_evidence=refs,
                        evaluation_mode=EvaluationMode.RULE_BASED,
                        model_name=None,
                    )
                else:
                    return ClaimEvaluation(
                        evaluation_id=eval_id,
                        claim_id=claim.claim_id,
                        company_ticker=claim.company_ticker,
                        company_name=claim.company_name,
                        claim_text=claim.claim_text,
                        claim_type=claim.claim_type,
                        category=claim.category,
                        category_group=claim.category_group,
                        assessment=AssessmentCategory.SUPPORTED,
                        confidence=EvaluationConfidence.MEDIUM,
                        reasoning=(
                            f"[Rule-Based Evaluation] The company's {cat_str} policy commitment is affirmed "
                            f"by formal disclosures in {top_sup.section_title}. Note that while this verifies the existence "
                            f"of the corporate policy, the filing does not report quantitative performance or representation outcome metrics."
                        ),
                        caveats=[
                            "Documented policy confirms corporate commitment, but filing lacks quantitative workforce representation or performance outcome data."
                        ],
                        referenced_evidence=refs,
                        evaluation_mode=EvaluationMode.RULE_BASED,
                        model_name=None,
                    )
            else:
                return ClaimEvaluation(
                    evaluation_id=eval_id,
                    claim_id=claim.claim_id,
                    company_ticker=claim.company_ticker,
                    company_name=claim.company_name,
                    claim_text=claim.claim_text,
                    claim_type=claim.claim_type,
                    category=claim.category,
                    category_group=claim.category_group,
                    assessment=AssessmentCategory.UNSUBSTANTIATED,
                    confidence=EvaluationConfidence.MEDIUM,
                    reasoning=(
                        f"[Rule-Based Evaluation] Filing lacks documentation or verification of the claimed {cat_str} policy standard."
                    ),
                    caveats=[f"Policy standard for {cat_str} not documented in filing."],
                    referenced_evidence=[],
                    evaluation_mode=EvaluationMode.RULE_BASED,
                    model_name=None,
                )

        # 6. Default fallback for general claims
        if supporting_items:
            top_sup = supporting_items[0]
            refs = [
                EvidenceReference(
                    evidence_id=top_sup.evidence_id,
                    section_id=top_sup.section_id,
                    relevance_score=top_sup.relevance_score,
                    relationship=top_sup.relationship,
                    quote=top_sup.evidence_text[:300],
                )
            ]
            return ClaimEvaluation(
                evaluation_id=eval_id,
                claim_id=claim.claim_id,
                company_ticker=claim.company_ticker,
                company_name=claim.company_name,
                claim_text=claim.claim_text,
                claim_type=claim.claim_type,
                category=claim.category,
                category_group=claim.category_group,
                assessment=AssessmentCategory.SUPPORTED,
                confidence=EvaluationConfidence.LOW,
                reasoning=f"[Rule-Based Evaluation] General sustainability assertion regarding {cat_str} supported by affirmative context in {top_sup.section_title}.",
                caveats=[],
                referenced_evidence=refs,
                evaluation_mode=EvaluationMode.RULE_BASED,
                model_name=None,
            )

        return ClaimEvaluation(
            evaluation_id=eval_id,
            claim_id=claim.claim_id,
            company_ticker=claim.company_ticker,
            company_name=claim.company_name,
            claim_text=claim.claim_text,
            claim_type=claim.claim_type,
            category=claim.category,
            category_group=claim.category_group,
            assessment=AssessmentCategory.UNSUBSTANTIATED,
            confidence=EvaluationConfidence.LOW,
            reasoning=f"[Rule-Based Evaluation] Contextual disclosures exist regarding {cat_str} but do not substantiate the claim.",
            caveats=[f"Substantiating metrics for {cat_str} absent."],
            referenced_evidence=[],
            evaluation_mode=EvaluationMode.RULE_BASED,
            model_name=None,
        )

    # ─────────────────────────────────────────────────────────
    # Live LLM Evaluation Engine
    # ─────────────────────────────────────────────────────────

    def evaluate_claim_with_llm(
        self,
        claim: Claim,
        evidence_list: List[Evidence],
    ) -> ClaimEvaluation:
        """Evaluate a claim against its evidence using OpenAI or compatible API.

        Strictly enforces:
        - Structured JSON schema validation
        - Verification that referenced evidence IDs match supplied evidence
        - Rejection of fabricated IDs or unsupported quotations
        - Safe fallback to rule-based evaluation if LLM fails or produces malformed output
        """
        # If no evidence exists, do not waste LLM call -> immediately return INSUFFICIENT_EVIDENCE
        if not evidence_list:
            return self.evaluate_claim_rule_based(claim, evidence_list)

        evidence_map = {e.evidence_id: e for e in evidence_list}

        # Build payload with strict evidence catalog
        evidence_payload = [
            {
                "evidence_id": e.evidence_id,
                "section": e.section_title,
                "relationship": e.relationship,
                "text": e.evidence_text,
            }
            for e in evidence_list[:8]  # cap at top 8 to stay well within token bounds
        ]

        user_content = json.dumps(
            {
                "claim": {
                    "claim_id": claim.claim_id,
                    "claim_text": claim.claim_text,
                    "claim_type": claim.claim_type,
                    "category": claim.category,
                    "metric": claim.metric,
                    "target_value": claim.target_value,
                    "target_year": claim.target_year,
                },
                "available_evidence": evidence_payload,
            },
            indent=2,
        )

        api_url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_EVALUATION_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": self.settings.LLM_TEMPERATURE,
        }

        try:
            logger.info("Calling LLM provider (%s) for claim: %s", self.settings.LLM_MODEL, claim.claim_id)
            response = self._client.post(api_url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()

            raw_choice = data["choices"][0]["message"]["content"]
            parsed_json = json.loads(raw_choice)
            raw_eval = LLMRawAssessment.model_validate(parsed_json)

            # Validate referenced IDs against supplied evidence
            valid_refs, rejected_ids = self.validate_and_build_references(
                raw_eval.referenced_evidence_ids,
                evidence_map,
            )

            # Guard: If model returned 'supported' or 'inconsistent' but fabricated all citations
            if raw_eval.assessment in (AssessmentCategory.SUPPORTED, AssessmentCategory.INCONSISTENT):
                if not valid_refs:
                    logger.warning(
                        "LLM claimed %s but provided 0 valid evidence IDs (rejected: %s). Falling back to rule-based.",
                        raw_eval.assessment,
                        rejected_ids,
                    )
                    return self.evaluate_claim_rule_based(claim, evidence_list)

            eval_id = self.generate_evaluation_id(claim.claim_id, EvaluationMode.LLM.value)
            return ClaimEvaluation(
                evaluation_id=eval_id,
                claim_id=claim.claim_id,
                company_ticker=claim.company_ticker,
                company_name=claim.company_name,
                claim_text=claim.claim_text,
                claim_type=claim.claim_type,
                category=claim.category,
                category_group=claim.category_group,
                assessment=raw_eval.assessment,
                confidence=raw_eval.confidence,
                reasoning=raw_eval.reasoning,
                caveats=raw_eval.caveats,
                referenced_evidence=valid_refs,
                evaluation_mode=EvaluationMode.LLM,
                model_name=self.settings.LLM_MODEL,
            )

        except Exception as err:
            logger.error("LLM evaluation failed for claim %s: %s. Falling back to rule-based evaluation.", claim.claim_id, err)
            fallback = self.evaluate_claim_rule_based(claim, evidence_list)
            # Annotate reasoning that fallback was triggered due to provider failure
            return fallback.model_copy(
                update={
                    "reasoning": f"{fallback.reasoning} (Note: Switched to rule-based evaluation due to provider error: {err})"
                }
            )

    # ─────────────────────────────────────────────────────────
    # Public Evaluation Dispatchers
    # ─────────────────────────────────────────────────────────

    def evaluate_claim(
        self,
        claim: Claim,
        evidence_list: List[Evidence],
    ) -> ClaimEvaluation:
        """Evaluate a single claim using active provider mode (LLM or rule-based fallback)."""
        if self.is_live_llm_available:
            return self.evaluate_claim_with_llm(claim, evidence_list)
        return self.evaluate_claim_rule_based(claim, evidence_list)

    def evaluate_claim_evidence_result(
        self,
        result: ClaimEvidenceResult,
    ) -> ClaimEvaluation:
        """Evaluate a ClaimEvidenceResult instance from Phase 5."""
        return self.evaluate_claim(result.claim, result.evidence)

    def evaluate_company_filing(
        self,
        company_ticker: str,
        filing_accession: Optional[str] = None,
    ) -> CompanyEvaluationResponse:
        """Execute end-to-end claim evaluation for a company's SEC 10-K filing.

        Pipeline:
        Ticker -> Company -> SEC Filing -> Document -> Claims -> Evidence -> Claim Evaluations.
        """
        ticker = normalize_and_validate_ticker(company_ticker)

        # 1. Resolve company metadata
        company = self.sec_service.get_company_by_ticker(ticker)

        # 2. Select prevailing filing
        if filing_accession:
            filings_resp = self.sec_service.get_company_filings(ticker)
            selected_filing = next((f for f in filings_resp.filings if f.accession_number == filing_accession), None)
            if not selected_filing:
                raise FilingNotFoundError(f"Filing accession '{filing_accession}' not found for {ticker}")
        else:
            latest_resp = self.sec_service.get_latest_annual_filing(ticker)
            selected_filing = latest_resp.filing

        # Check in-memory cache
        if self.settings.EVALUATION_CACHE_IN_MEMORY and selected_filing.accession_number in self._evaluation_cache:
            summary, cached_evals = self._evaluation_cache[selected_filing.accession_number]
            return CompanyEvaluationResponse(
                company=company,
                filing_accession_number=selected_filing.accession_number,
                form_type=selected_filing.form_type,
                filing_date=selected_filing.filing_date,
                report_date=selected_filing.report_date,
                fiscal_year=selected_filing.fiscal_year,
                summary=summary,
                evaluations=cached_evals,
                provider_mode=self.active_provider_mode,
                model_name=self.settings.LLM_MODEL if self.is_live_llm_available else None,
            )

        # 3. Retrieve evidence results
        evidence_resp = self.evidence_service.get_company_evidence(ticker=ticker, limit=500)
        evidence_results = evidence_resp.results

        total_claims_extracted = len(evidence_results)
        valid_results: List[ClaimEvidenceResult] = []
        excluded_count = 0
        for ev_res in evidence_results:
            is_valid, reason = self.is_sustainability_claim(ev_res.claim)
            if not is_valid:
                logger.info(
                    "Excluding non-sustainability claim %s (%s): %s",
                    ev_res.claim.claim_id,
                    reason,
                    ev_res.claim.claim_text,
                )
                excluded_count += 1
            else:
                valid_results.append(ev_res)

        # 4. Evaluate each valid claim
        evaluations: List[ClaimEvaluation] = []
        for ev_res in valid_results:
            evaluation = self.evaluate_claim_evidence_result(ev_res)
            evaluations.append(evaluation)

        summary = self._compute_summary(
            evaluations,
            total_claims_extracted=total_claims_extracted,
            excluded_claims_count=excluded_count,
        )

        # Cache results
        if self.settings.EVALUATION_CACHE_IN_MEMORY:
            self._evaluation_cache[selected_filing.accession_number] = (summary, evaluations)

        return CompanyEvaluationResponse(
            company=company,
            filing_accession_number=selected_filing.accession_number,
            form_type=selected_filing.form_type,
            filing_date=selected_filing.filing_date,
            report_date=selected_filing.report_date,
            fiscal_year=selected_filing.fiscal_year,
            summary=summary,
            evaluations=evaluations,
            provider_mode=self.active_provider_mode,
            model_name=self.settings.LLM_MODEL if self.is_live_llm_available else None,
        )

    def get_single_claim_evaluation(
        self,
        company_ticker: str,
        claim_id: str,
    ) -> SingleClaimEvaluationResponse:
        """Retrieve or compute evaluation for a specific claim ID."""
        comp_eval = self.evaluate_company_filing(company_ticker)
        for ev in comp_eval.evaluations:
            if ev.claim_id == claim_id:
                return SingleClaimEvaluationResponse(
                    evaluation=ev,
                    provider_mode=comp_eval.provider_mode,
                )
        raise ClaimNotFoundError(f"Claim ID '{claim_id}' not found in evaluations for {company_ticker}")

    # ─────────────────────────────────────────────────────────
    # Summary Computation Helper
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _compute_summary(
        evaluations: List[ClaimEvaluation],
        total_claims_extracted: int = 0,
        excluded_claims_count: int = 0,
    ) -> EvaluationSummary:
        """Compute aggregate summary distribution of evaluations."""
        summary = EvaluationSummary(
            total_claims_evaluated=len(evaluations),
            total_claims_extracted=total_claims_extracted or len(evaluations),
            excluded_claims_count=excluded_claims_count,
        )
        for ev in evaluations:
            if ev.assessment == AssessmentCategory.SUPPORTED:
                summary.supported_count += 1
            elif ev.assessment == AssessmentCategory.PARTIALLY_SUPPORTED:
                summary.partially_supported_count += 1
            elif ev.assessment == AssessmentCategory.INCONSISTENT:
                summary.inconsistent_count += 1
            elif ev.assessment == AssessmentCategory.UNSUBSTANTIATED:
                summary.unsubstantiated_count += 1
            elif ev.assessment == AssessmentCategory.INSUFFICIENT_EVIDENCE:
                summary.insufficient_evidence_count += 1

            if ev.evaluation_mode == EvaluationMode.RULE_BASED:
                summary.rule_based_evaluations_count += 1
            elif ev.evaluation_mode == EvaluationMode.LLM:
                summary.llm_evaluations_count += 1

        return summary


# Singleton instance
_llm_service_instance: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Return a singleton instance of LLMService."""
    global _llm_service_instance
    if _llm_service_instance is None:
        _llm_service_instance = LLMService()
    return _llm_service_instance
