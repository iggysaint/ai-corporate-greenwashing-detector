"""ESG Integrity Scoring Service (Phase 8).

Deterministic, explainable synthesis of claim evaluations into an ESG Integrity Score.
Full methodology and rationale: docs/ESG_INTEGRITY_SCORE_METHODOLOGY.md

IMPORTANT SCOPE:
    The ESG Integrity Score measures ONLY how well a company's disclosed sustainability
    claims are substantiated by the evidence retrieved from the analysed disclosure documents.
    It is NOT an ESG performance rating, NOT a measure of total environmental or social
    impact, NOT proof that a company is or is not greenwashing, and NOT a substitute for an
    independent ESG audit.

Design rules enforced here:
    - No LLM decides any number. Scores are pure functions of evaluation inputs + configuration.
    - INSUFFICIENT_EVIDENCE is excluded from the score and reported via evidence coverage.
    - UNSUBSTANTIATED receives partial credit; it is never treated as proven false.
    - Assessment categories map to non-overlapping score bands.
    - Low-materiality statements are volume-damped so they cannot swamp material claims.
    - No numerical score is produced below a minimum number of assessable claims.
"""

from datetime import datetime, timezone
import logging
import re
from typing import Dict, List, Optional, Tuple

from app.models.claim import ClaimType
from app.models.evaluation import (
    AssessmentCategory,
    ClaimEvaluation,
    CompanyEvaluationResponse,
    EvaluationConfidence,
    EvaluationMode,
)
from app.models.market import (
    DocumentSourceType,
    GSEAnalysisResponse,
    GSECompany,
    MarketIdentifier,
)
from app.models.scoring import (
    ClaimScoreDetail,
    ConfidenceLevel,
    DimensionalScore,
    ESGIntegrityScoreResponse,
    ESGScoreBreakdownResponse,
    ESGScoreHistoryResponse,
    ScoreStatus,
)
from app.services.gse_service import GHANA_ESG_SECTORS, GSEService, get_gse_service, normalize_gse_ticker
from app.services.llm_service import LLMService, get_llm_service
from app.services.sec_service import normalize_and_validate_ticker
from app.utils.config import Settings, get_settings

logger = logging.getLogger(__name__)

PILLARS: Tuple[str, ...] = ("environmental", "social", "governance")

# ─────────────────────────────────────────────────────────
# Methodology constants (see methodology document for rationale)
# ─────────────────────────────────────────────────────────

# (base score, band minimum, band maximum) per assessment category.
# Bands do not overlap, so quality adjustments can never make a partially supported claim
# outrank a supported one, or an unsubstantiated claim outrank a partially supported one.
ASSESSMENT_BANDS: Dict[AssessmentCategory, Tuple[float, float, float]] = {
    AssessmentCategory.SUPPORTED: (90.0, 80.0, 100.0),
    AssessmentCategory.PARTIALLY_SUPPORTED: (60.0, 50.0, 70.0),
    AssessmentCategory.UNSUBSTANTIATED: (25.0, 15.0, 35.0),
    AssessmentCategory.INCONSISTENT: (0.0, 0.0, 0.0),
    # INSUFFICIENT_EVIDENCE has no band: it is excluded from scores (see evidence coverage).
}

# Materiality weight by claim type: measurable outcomes > commitments > policies > general statements.
CLAIM_TYPE_MATERIALITY: Dict[str, float] = {
    ClaimType.ACHIEVEMENT.value: 1.5,
    ClaimType.CURRENT_STATE.value: 1.2,
    ClaimType.TARGET.value: 1.3,
    ClaimType.POLICY.value: 0.9,
    ClaimType.GENERAL.value: 0.6,
}
DEFAULT_TYPE_MATERIALITY = 0.6  # unknown claim types are treated as general statements
QUANTIFIED_MULTIPLIER = 1.2
SECTOR_PRIORITY_MULTIPLIER = 1.3

# Evidence quality adjustments (points, applied inside the category band)
ADJ_HIGH_CONFIDENCE = 3.0
ADJ_LOW_CONFIDENCE = -3.0
ADJ_HIGH_RELEVANCE = 3.0       # mean cited relevance >= 0.40
ADJ_LOW_RELEVANCE = -3.0       # mean cited relevance < 0.20
ADJ_NO_CITATION = -3.0         # non-inconsistent claim with no validated evidence citation
ADJ_PER_CAVEAT = -2.0
ADJ_MAX_CAVEAT_TOTAL = -6.0
ADJ_LIMIT = 10.0

# Quantitative specificity: percentages, currency amounts, numbers with physical/workforce units,
# or an explicit deadline year ("by 2030"). Bare 4-digit years are deliberately NOT counted:
# page headers such as "2024 Annual Report" would otherwise mark almost every claim as quantified.
QUANTITATIVE_PATTERN = re.compile(
    r"(?:\d+(?:\.\d+)?\s?%"
    r"|(?:\$|US\$|GH[S¢₵]|GHC)\s?\d"
    r"|\b\d[\d,]*(?:\.\d+)?\s*(?:metric\s+tons?|tonnes?|tons?|tco2e?|mwh|gwh|kwh|mw|litres?|liters?|"
    r"gallons?|m3|hectares?|employees|workers|individuals|people|beneficiaries|directors)\b"
    r"|\b(?:by|before|until|through)\s+20\d{2}\b)",
    re.I,
)

# Sector materiality profiles. Identical profiles apply to US SEC and GSE companies:
# the market never changes how a claim is scored, only the company's sector does.
# Each profile: (sector alias pattern, material claim categories, material keywords)
SECTOR_PROFILES: List[Tuple[str, re.Pattern, set, List[str]]] = [
    (
        "mining",
        re.compile(r"\b(?:mining|mines?|gold|minerals?|metal\s+ores?)\b", re.I),
        {"water", "pollution", "waste", "biodiversity", "environmental_management",
         "health_and_safety", "community", "human_rights"},
        GHANA_ESG_SECTORS["mining"] + ["land rehabilitation", "rehabilitation", "reclamation", "cyanide"],
    ),
    (
        "oil_and_gas",
        re.compile(r"\b(?:oil|gas|petroleum|crude|refin\w*)\b", re.I),
        {"emissions", "greenhouse_gas", "carbon", "climate", "pollution", "environmental_management",
         "health_and_safety", "community"},
        GHANA_ESG_SECTORS["oil_and_gas"],
    ),
    (
        "agriculture",
        re.compile(r"\b(?:agricultur\w*|cocoa|plantations?|palm|farming|agro\w*)\b", re.I),
        {"biodiversity", "water", "supply_chain", "labor", "human_rights", "community"},
        GHANA_ESG_SECTORS["agriculture"],
    ),
    (
        "banking",
        re.compile(r"\b(?:bank\w*|financ\w*|insurance|microfinance|savings)\b", re.I),
        {"governance", "ethics", "compliance", "risk_management", "transparency", "business_conduct",
         "inclusion"},
        GHANA_ESG_SECTORS["banking"] + ["anti-money laundering", "data protection"],
    ),
    (
        "telecommunications",
        re.compile(r"\b(?:telecom\w*|mobile|wireless)\b", re.I),
        {"energy", "renewable_energy", "carbon", "emissions", "greenhouse_gas", "waste", "inclusion"},
        GHANA_ESG_SECTORS["telecommunications"] + ["financial inclusion", "mobile money", "data privacy"],
    ),
    (
        "technology",
        re.compile(r"\b(?:computers?|electronic\w*|software|semiconductors?|technology)\b", re.I),
        {"energy", "renewable_energy", "carbon", "emissions", "greenhouse_gas", "supply_chain",
         "recycling", "waste", "human_rights"},
        ["e-waste", "conflict minerals", "data privacy"],
    ),
    (
        "manufacturing",
        re.compile(r"\b(?:manufactur\w*|industrial|cement|steel|chemicals?)\b", re.I),
        {"emissions", "energy", "waste", "pollution", "water", "health_and_safety", "labor"},
        GHANA_ESG_SECTORS["manufacturing"],
    ),
    (
        "consumer_goods",
        re.compile(r"\b(?:consumer|beverages?|brewer\w*|food|household|distribution)\b", re.I),
        {"waste", "recycling", "water", "supply_chain", "circular_economy"},
        ["packaging", "plastics", "plastic"],
    ),
]


def _truncate(text: str, limit: int = 90) -> str:
    """Single-line truncation for human-readable factor strings."""
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 3] + "..."


def _round_score(value: float) -> float:
    """Round scores to whole points: the methodology does not support finer precision."""
    return float(round(value))


class ScoringService:
    """Deterministic and explainable ESG Integrity Scoring Service."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        llm_service: Optional[LLMService] = None,
        gse_service: Optional[GSEService] = None,
    ):
        self.settings = settings or get_settings()
        self._llm_service = llm_service
        self._gse_service = gse_service
        # In-memory only (no database in this phase). Keys are market-qualified to keep
        # US SEC and GSE tickers separate.
        self._score_cache: Dict[str, ESGScoreBreakdownResponse] = {}
        self._score_history: Dict[str, Dict[str, ESGIntegrityScoreResponse]] = {}

    @property
    def llm_service(self) -> LLMService:
        if self._llm_service is None:
            self._llm_service = get_llm_service()
        return self._llm_service

    @property
    def gse_service(self) -> GSEService:
        if self._gse_service is None:
            self._gse_service = get_gse_service()
        return self._gse_service

    def clear_cache(self) -> None:
        """Clear in-memory scores and history."""
        self._score_cache.clear()
        self._score_history.clear()

    @staticmethod
    def _key(market: MarketIdentifier, ticker: str) -> str:
        return f"{market.value}:{ticker.strip().upper()}"

    # ─────────────────────────────────────────────────────────
    # Pure calculation engine
    # ─────────────────────────────────────────────────────────

    def calculate_score_from_evaluations(
        self,
        company_name: str,
        ticker: str,
        market: MarketIdentifier,
        evaluations: List[ClaimEvaluation],
        total_claims_extracted: int,
        reporting_period: Optional[str] = None,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        source_document_references: Optional[List[str]] = None,
    ) -> ESGScoreBreakdownResponse:
        """Compute the ESG Integrity Score from claim evaluations. Pure and deterministic
        (apart from the assessment timestamp)."""
        s = self.settings
        sector_profile = self._match_sector_profile(sector, industry)

        # 1. De-duplicate by claim_id (first occurrence wins) so a claim cannot be counted twice.
        seen: set = set()
        unique_evals: List[ClaimEvaluation] = []
        for ev in evaluations:
            if ev.claim_id in seen:
                continue
            seen.add(ev.claim_id)
            unique_evals.append(ev)
        duplicates_ignored = len(evaluations) - len(unique_evals)

        # 2. Claim-level scores
        details = [self._score_claim(ev, sector_profile) for ev in unique_evals]

        counts = {cat: 0 for cat in AssessmentCategory}
        for d in details:
            counts[d.assessment] += 1

        mapped = [d for d in details if d.category_group.lower() in PILLARS]
        unmapped_count = len(details) - len(mapped)
        assessable = [d for d in mapped if d.assessment != AssessmentCategory.INSUFFICIENT_EVIDENCE]

        total_assessed = len(details)
        insufficient = counts[AssessmentCategory.INSUFFICIENT_EVIDENCE]
        evidence_coverage = (
            _round_score((total_assessed - insufficient) / total_assessed * 100.0) if total_assessed else 0.0
        )
        substantiated = sum(
            1 for d in assessable
            if d.assessment in (AssessmentCategory.SUPPORTED, AssessmentCategory.PARTIALLY_SUPPORTED)
        )
        substantiation_rate = _round_score(substantiated / len(assessable) * 100.0) if assessable else None

        rule_based_n = sum(1 for e in unique_evals if e.evaluation_mode == EvaluationMode.RULE_BASED)
        llm_n = sum(1 for e in unique_evals if e.evaluation_mode == EvaluationMode.LLM)
        all_rule_based = bool(unique_evals) and llm_n == 0

        # 3. Pillar scores (with low-materiality volume damping)
        base_weights = {
            "environmental": s.SCORE_WEIGHT_ENVIRONMENTAL,
            "social": s.SCORE_WEIGHT_SOCIAL,
            "governance": s.SCORE_WEIGHT_GOVERNANCE,
        }
        raw_pillar_scores: Dict[str, Optional[float]] = {}
        dimensions: Dict[str, DimensionalScore] = {}
        for pillar in PILLARS:
            dim, raw = self._score_pillar(pillar, details, base_weights[pillar], all_rule_based)
            dimensions[pillar] = dim
            raw_pillar_scores[pillar] = raw

        # 4. Overall score: configured pillar weights, scaled down for thinly evidenced pillars,
        #    renormalised over pillars that could be scored.
        min_claims = max(1, s.SCORE_MIN_ASSESSABLE_CLAIMS)
        pillar_eff: Dict[str, float] = {}
        for pillar, dim in dimensions.items():
            if dim.status == ScoreStatus.SCORED:
                sufficiency = min(1.0, dim.assessable_claims_count / min_claims)
                pillar_eff[pillar] = base_weights[pillar] * sufficiency
        eff_total = sum(pillar_eff.values())
        for pillar, dim in dimensions.items():
            dim.effective_weight = round(pillar_eff[pillar] / eff_total, 3) if pillar in pillar_eff and eff_total else 0.0

        insufficient_reason: Optional[str] = None
        if len(assessable) < min_claims or eff_total <= 0:
            overall: Optional[float] = None
            status = ScoreStatus.INSUFFICIENT_DATA
            confidence = ConfidenceLevel.INSUFFICIENT
            insufficient_reason = (
                f"Only {len(assessable)} assessable claim(s) mapped to E/S/G; at least {min_claims} are required "
                "before an overall score is produced. This reflects limited disclosure data, not a low score."
            )
        else:
            overall = _round_score(
                sum(pillar_eff[p] * raw_pillar_scores[p] for p in pillar_eff) / eff_total
            )
            status = ScoreStatus.SCORED
            confidence = self._overall_confidence(len(assessable), evidence_coverage, dimensions, all_rule_based)

        positives, concerns = self._factors_and_concerns(
            details, dimensions, evidence_coverage, substantiation_rate, all_rule_based, insufficient_reason,
        )

        return ESGScoreBreakdownResponse(
            company_name=company_name,
            ticker=ticker,
            market=market,
            reporting_period=reporting_period,
            esg_integrity_score=overall,
            score_status=status,
            confidence=confidence,
            evidence_coverage=evidence_coverage,
            substantiation_rate=substantiation_rate,
            environmental_score=dimensions["environmental"].score,
            social_score=dimensions["social"].score,
            governance_score=dimensions["governance"].score,
            total_claims_extracted=max(total_claims_extracted, total_assessed),
            total_claims_assessed=total_assessed,
            supported_claims=counts[AssessmentCategory.SUPPORTED],
            partially_supported_claims=counts[AssessmentCategory.PARTIALLY_SUPPORTED],
            inconsistent_claims=counts[AssessmentCategory.INCONSISTENT],
            unsubstantiated_claims=counts[AssessmentCategory.UNSUBSTANTIATED],
            insufficient_evidence_claims=insufficient,
            unmapped_claims=unmapped_count,
            duplicate_evaluations_ignored=duplicates_ignored,
            rule_based_evaluations=rule_based_n,
            llm_evaluations=llm_n,
            main_positive_factors=positives,
            main_concerns=concerns,
            methodology_version=s.SCORING_METHODOLOGY_VERSION,
            assessment_timestamp=datetime.now(timezone.utc).isoformat(),
            source_document_references=source_document_references or [],
            dimensions=dimensions,
            claim_scores=details,
            materiality_summary={
                "sector": sector,
                "industry": industry,
                "matched_sector_profile": sector_profile[0] if sector_profile else None,
                "sector_priority_matches": sum(1 for d in details if d.sector_priority_match),
                "quantified_claims": sum(1 for d in details if d.is_quantified),
            },
            methodology_details={
                "version": s.SCORING_METHODOLOGY_VERSION,
                "assessment_bands": {
                    k.value: {"base": v[0], "min": v[1], "max": v[2]} for k, v in ASSESSMENT_BANDS.items()
                },
                "insufficient_evidence_treatment": "excluded from scores; reduces evidence_coverage",
                "claim_type_materiality": CLAIM_TYPE_MATERIALITY,
                "quantified_multiplier": QUANTIFIED_MULTIPLIER,
                "sector_priority_multiplier": SECTOR_PRIORITY_MULTIPLIER,
                "low_materiality_threshold": s.SCORE_LOW_MATERIALITY_THRESHOLD,
                "low_materiality_max_share": s.SCORE_LOW_MATERIALITY_MAX_SHARE,
                "pillar_base_weights": base_weights,
                "min_assessable_claims": min_claims,
                "confidence_capped_for_rule_based": s.SCORE_CAP_CONFIDENCE_FOR_RULE_BASED and all_rule_based,
                "rounding": "scores and percentages rounded to whole numbers",
            },
        )

    # ─────────────────────────────────────────────────────────
    # Claim-level scoring
    # ─────────────────────────────────────────────────────────

    def _score_claim(self, ev: ClaimEvaluation, sector_profile) -> ClaimScoreDetail:
        is_quantified = bool(QUANTITATIVE_PATTERN.search(ev.claim_text))
        sector_match = self._sector_priority(ev, sector_profile)
        weight = CLAIM_TYPE_MATERIALITY.get(ev.claim_type, DEFAULT_TYPE_MATERIALITY)
        if is_quantified:
            weight *= QUANTIFIED_MULTIPLIER
        if sector_match:
            weight *= SECTOR_PRIORITY_MULTIPLIER
        weight = round(weight, 3)

        adjustment, reasons = 0.0, []
        if ev.assessment == AssessmentCategory.INSUFFICIENT_EVIDENCE:
            base, score = 0.0, 0.0
            reasons.append("Insufficient evidence: excluded from scoring (reflected in evidence coverage).")
        elif ev.assessment == AssessmentCategory.INCONSISTENT:
            base, score = 0.0, 0.0
            reasons.append("Inconsistent: fixed at 0; evidence quality cannot offset a contradiction.")
        else:
            base, band_min, band_max = ASSESSMENT_BANDS[ev.assessment]
            adjustment, reasons = self._quality_adjustment(ev)
            score = min(band_max, max(band_min, base + adjustment))

        return ClaimScoreDetail(
            claim_id=ev.claim_id,
            evaluation_id=ev.evaluation_id,
            claim_text=ev.claim_text,
            claim_type=ev.claim_type,
            category=ev.category,
            category_group=ev.category_group,
            assessment=ev.assessment,
            base_score=base,
            evidence_quality_adjustment=adjustment,
            quality_adjustment_reasons=reasons,
            claim_score=score,
            materiality_weight=weight,
            is_quantified=is_quantified,
            sector_priority_match=sector_match,
            referenced_evidence_ids=[r.evidence_id for r in ev.referenced_evidence],
            referenced_evidence=list(ev.referenced_evidence),
            caveats_count=len(ev.caveats),
            reasoning=ev.reasoning,
        )

    @staticmethod
    def _quality_adjustment(ev: ClaimEvaluation) -> Tuple[float, List[str]]:
        adj, reasons = 0.0, []
        if ev.confidence == EvaluationConfidence.HIGH:
            adj += ADJ_HIGH_CONFIDENCE
            reasons.append(f"+{ADJ_HIGH_CONFIDENCE:g}: high evaluation confidence")
        elif ev.confidence == EvaluationConfidence.LOW:
            adj += ADJ_LOW_CONFIDENCE
            reasons.append(f"{ADJ_LOW_CONFIDENCE:g}: low evaluation confidence")

        if ev.referenced_evidence:
            mean_rel = sum(r.relevance_score for r in ev.referenced_evidence) / len(ev.referenced_evidence)
            if mean_rel >= 0.40:
                adj += ADJ_HIGH_RELEVANCE
                reasons.append(f"+{ADJ_HIGH_RELEVANCE:g}: mean cited-evidence relevance {mean_rel:.2f} >= 0.40")
            elif mean_rel < 0.20:
                adj += ADJ_LOW_RELEVANCE
                reasons.append(f"{ADJ_LOW_RELEVANCE:g}: mean cited-evidence relevance {mean_rel:.2f} < 0.20")
        else:
            adj += ADJ_NO_CITATION
            reasons.append(f"{ADJ_NO_CITATION:g}: no validated evidence citation")

        if ev.caveats:
            caveat_adj = max(ADJ_MAX_CAVEAT_TOTAL, ADJ_PER_CAVEAT * len(ev.caveats))
            adj += caveat_adj
            reasons.append(f"{caveat_adj:g}: {len(ev.caveats)} caveat(s) noted in evaluation")

        adj = max(-ADJ_LIMIT, min(ADJ_LIMIT, adj))
        return adj, reasons

    # ─────────────────────────────────────────────────────────
    # Sector materiality
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _match_sector_profile(sector: Optional[str], industry: Optional[str]):
        """Return the first matching sector profile (deterministic order) or None."""
        text = " ".join(x for x in (sector, industry) if x)
        if not text:
            return None
        for profile in SECTOR_PROFILES:
            if profile[1].search(text):
                return profile
        return None

    @staticmethod
    def _sector_priority(ev: ClaimEvaluation, profile) -> bool:
        if profile is None:
            return False
        _, _, categories, keywords = profile
        if ev.category.lower() in categories:
            return True
        text = ev.claim_text.lower()
        return any(re.search(r"\b" + re.escape(kw.lower()) + r"\b", text) for kw in keywords)

    # ─────────────────────────────────────────────────────────
    # Pillar aggregation
    # ─────────────────────────────────────────────────────────

    def _score_pillar(
        self,
        pillar: str,
        details: List[ClaimScoreDetail],
        base_weight: float,
        all_rule_based: bool,
    ) -> Tuple[DimensionalScore, Optional[float]]:
        s = self.settings
        claims = [d for d in details if d.category_group.lower() == pillar]
        by_cat = {cat: sum(1 for d in claims if d.assessment == cat) for cat in AssessmentCategory}
        assessable = [d for d in claims if d.assessment != AssessmentCategory.INSUFFICIENT_EVIDENCE]
        n = len(claims)
        insufficient = by_cat[AssessmentCategory.INSUFFICIENT_EVIDENCE]
        coverage = _round_score((n - insufficient) / n * 100.0) if n else 0.0

        common = dict(
            dimension=pillar,
            weight=base_weight,
            effective_weight=0.0,
            claims_count=n,
            assessable_claims_count=len(assessable),
            supported_count=by_cat[AssessmentCategory.SUPPORTED],
            partially_supported_count=by_cat[AssessmentCategory.PARTIALLY_SUPPORTED],
            inconsistent_count=by_cat[AssessmentCategory.INCONSISTENT],
            unsubstantiated_count=by_cat[AssessmentCategory.UNSUBSTANTIATED],
            insufficient_evidence_count=insufficient,
            evidence_coverage=coverage,
        )

        if not assessable:
            reason = (
                "No claims extracted for this pillar." if n == 0
                else f"All {n} claim(s) lacked relevant evidence."
            )
            return DimensionalScore(
                **common,
                score=None,
                status=ScoreStatus.INSUFFICIENT_DATA,
                confidence=ConfidenceLevel.INSUFFICIENT,
                key_factors=[f"Insufficient data: {reason} Pillar not scored (a data gap, not a zero)."],
            ), None

        # Volume damping: low-materiality claims collectively hold at most MAX_SHARE of pillar weight.
        threshold = s.SCORE_LOW_MATERIALITY_THRESHOLD
        share = min(max(s.SCORE_LOW_MATERIALITY_MAX_SHARE, 0.0), 0.95)
        high = [d for d in assessable if d.materiality_weight >= threshold]
        low = [d for d in assessable if d.materiality_weight < threshold]
        high_sum = sum(d.materiality_weight for d in high)
        low_sum = sum(d.materiality_weight for d in low)
        low_scale = 1.0
        if high_sum > 0 and low_sum > 0:
            cap = high_sum * share / (1.0 - share)
            if low_sum > cap:
                low_scale = cap / low_sum
        for d in high:
            d.effective_weight = d.materiality_weight
            d.included_in_score = True
        for d in low:
            d.effective_weight = round(d.materiality_weight * low_scale, 4)
            d.included_in_score = True

        w_total = sum(d.effective_weight for d in assessable)
        raw = sum(d.effective_weight * d.claim_score for d in assessable) / w_total if w_total else 0.0

        factors: List[str] = []
        if common["supported_count"]:
            factors.append(f"{common['supported_count']} claim(s) supported by retrieved evidence.")
        if common["partially_supported_count"]:
            factors.append(f"{common['partially_supported_count']} claim(s) partially supported (caveats or scope limits).")
        if common["inconsistent_count"]:
            factors.append(f"{common['inconsistent_count']} claim(s) contradicted by retrieved evidence.")
        if common["unsubstantiated_count"]:
            factors.append(
                f"{common['unsubstantiated_count']} claim(s) unsubstantiated: relevant disclosures found but they "
                "do not establish the claim."
            )
        if insufficient:
            factors.append(f"{insufficient} claim(s) excluded for insufficient evidence.")
        if low_scale < 1.0:
            factors.append(
                f"Volume damping applied: {len(low)} low-materiality statement(s) capped at "
                f"{int(share * 100)}% of pillar weight."
            )

        k = len(assessable)
        if k >= 5 and coverage >= 70:
            conf = ConfidenceLevel.HIGH
        elif k >= 3:
            conf = ConfidenceLevel.MEDIUM
        else:
            conf = ConfidenceLevel.LOW
        if conf == ConfidenceLevel.HIGH and all_rule_based and s.SCORE_CAP_CONFIDENCE_FOR_RULE_BASED:
            conf = ConfidenceLevel.MEDIUM

        return DimensionalScore(
            **common,
            score=_round_score(raw),
            status=ScoreStatus.SCORED,
            confidence=conf,
            key_factors=factors,
        ), raw

    def _overall_confidence(
        self,
        assessable_n: int,
        coverage: float,
        dimensions: Dict[str, DimensionalScore],
        all_rule_based: bool,
    ) -> ConfidenceLevel:
        scored_pillars = sum(1 for d in dimensions.values() if d.status == ScoreStatus.SCORED)
        if assessable_n >= 10 and coverage >= 70 and scored_pillars >= 2:
            conf = ConfidenceLevel.HIGH
        elif assessable_n >= 5 and coverage >= 50:
            conf = ConfidenceLevel.MEDIUM
        else:
            conf = ConfidenceLevel.LOW
        if conf == ConfidenceLevel.HIGH and all_rule_based and self.settings.SCORE_CAP_CONFIDENCE_FOR_RULE_BASED:
            conf = ConfidenceLevel.MEDIUM
        return conf

    # ─────────────────────────────────────────────────────────
    # Explanations (derived only from computed results; no LLM)
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _factors_and_concerns(
        details: List[ClaimScoreDetail],
        dimensions: Dict[str, DimensionalScore],
        coverage: float,
        substantiation_rate: Optional[float],
        all_rule_based: bool,
        insufficient_reason: Optional[str],
    ) -> Tuple[List[str], List[str]]:
        positives: List[str] = []
        concerns: List[str] = []
        by_weight = sorted(details, key=lambda d: (-d.materiality_weight, d.claim_id))

        for d in [x for x in by_weight if x.assessment == AssessmentCategory.SUPPORTED][:3]:
            positives.append(
                f"Supported {d.claim_type} claim ({d.category}, materiality {d.materiality_weight:g}): "
                f"'{_truncate(d.claim_text)}' [{d.claim_id}]"
            )
        for d in [x for x in by_weight if x.assessment == AssessmentCategory.PARTIALLY_SUPPORTED][:2]:
            positives.append(
                f"Partially supported {d.claim_type} claim ({d.category}); evidence covers only part of the claim: "
                f"'{_truncate(d.claim_text)}' [{d.claim_id}]"
            )
        for dim in dimensions.values():
            if dim.score is not None and dim.score >= 70 and dim.assessable_claims_count >= 3:
                positives.append(
                    f"{dim.dimension.capitalize()} pillar scored {dim.score:g}/100 across "
                    f"{dim.assessable_claims_count} assessable claims."
                )

        if insufficient_reason:
            concerns.append(insufficient_reason)
        for d in [x for x in by_weight if x.assessment == AssessmentCategory.INCONSISTENT][:3]:
            concerns.append(
                f"Contradicted {d.claim_type} claim ({d.category}): retrieved evidence conflicts with "
                f"'{_truncate(d.claim_text)}' [{d.claim_id}]"
            )
        material_types = {ClaimType.ACHIEVEMENT.value, ClaimType.TARGET.value, ClaimType.CURRENT_STATE.value}
        for d in [x for x in by_weight
                  if x.assessment == AssessmentCategory.UNSUBSTANTIATED and x.claim_type in material_types][:3]:
            concerns.append(
                f"Unsubstantiated {d.claim_type} claim ({d.category}): retrieved disclosures do not establish "
                f"'{_truncate(d.claim_text)}' [{d.claim_id}]. This is not a finding that the claim is false."
            )
        if substantiation_rate is not None and substantiation_rate < 50:
            concerns.append(
                f"Only {substantiation_rate:g}% of assessable claims are supported or partially supported."
            )
        insufficient_n = sum(1 for d in details if d.assessment == AssessmentCategory.INSUFFICIENT_EVIDENCE)
        if insufficient_n:
            concerns.append(
                f"{insufficient_n} claim(s) could not be assessed (no relevant evidence retrieved); excluded from "
                f"the score and reflected in evidence coverage ({coverage:g}%)."
            )
        unscored = [d.dimension.capitalize() for d in dimensions.values() if d.status == ScoreStatus.INSUFFICIENT_DATA]
        if unscored and not insufficient_reason:
            concerns.append(
                f"No assessable claims for: {', '.join(unscored)}. These pillars are not scored (data gap, not zero)."
            )
        if all_rule_based:
            concerns.append(
                "All evaluations were produced by the deterministic rule-based engine (keyword and evidence-relationship "
                "heuristics, not full reading comprehension); confidence is capped at medium."
            )
        return positives, concerns

    # ─────────────────────────────────────────────────────────
    # SEC and GSE workflow integration
    # ─────────────────────────────────────────────────────────

    def calculate_company_score(self, ticker: str) -> ESGScoreBreakdownResponse:
        """Score a US company from its latest SEC annual filing (via existing Phase 6 evaluations)."""
        clean = normalize_and_validate_ticker(ticker)
        resp: CompanyEvaluationResponse = self.llm_service.evaluate_company_filing(clean)
        company = resp.company

        if resp.fiscal_year:
            period = f"FY{resp.fiscal_year}"
        elif resp.report_date:
            period = f"Period ending {resp.report_date}"
        else:
            period = None  # not invented from the filing date

        refs = [
            f"SEC EDGAR Form {resp.form_type}, accession {resp.filing_accession_number}, filed {resp.filing_date}"
            + (f", period ending {resp.report_date}" if resp.report_date else "")
        ]
        breakdown = self.calculate_score_from_evaluations(
            company_name=company.company_name,
            ticker=company.ticker,
            market=MarketIdentifier.US_SEC,
            evaluations=resp.evaluations,
            total_claims_extracted=resp.summary.total_claims_extracted,
            reporting_period=period,
            sector=company.sic_description,
            industry=None,
            source_document_references=refs,
        )
        self._store(MarketIdentifier.US_SEC, clean, resp.filing_accession_number, breakdown)
        return breakdown

    def calculate_gse_score(
        self,
        ticker: str,
        source_url: Optional[str] = None,
        source_type: DocumentSourceType = DocumentSourceType.ANNUAL_REPORT,
        reporting_period: Optional[str] = None,
    ) -> ESGScoreBreakdownResponse:
        """Score a GSE company from a disclosure document (via existing Phase 7A analysis pipeline)."""
        clean = normalize_gse_ticker(ticker)
        resp: GSEAnalysisResponse = self.gse_service.analyze_company_document(
            ticker=clean,
            source_url=source_url,
            source_type=source_type,
            reporting_period=reporting_period,
        )
        company: GSECompany = resp.company
        doc = resp.document
        refs = [
            f"{doc.title} ({doc.source_type.value}, {doc.format}, period {doc.reporting_period or 'unknown'}, "
            f"document_id {doc.document_id})"
        ]
        if doc.source_url:
            refs.append(doc.source_url)

        breakdown = self.calculate_score_from_evaluations(
            company_name=company.company_name,
            ticker=company.ticker,
            market=MarketIdentifier.GH_GSE,
            evaluations=resp.evaluations,
            total_claims_extracted=resp.total_claims_extracted,
            reporting_period=doc.reporting_period,
            sector=company.sector,
            industry=company.industry,
            source_document_references=refs,
        )
        self._store(MarketIdentifier.GH_GSE, clean, doc.document_id, breakdown)
        return breakdown

    def _store(self, market: MarketIdentifier, ticker: str, document_key: str, breakdown: ESGScoreBreakdownResponse) -> None:
        """Cache the latest score and record one history entry per distinct document and
        methodology version (re-scoring the same document replaces its entry)."""
        key = self._key(market, ticker)
        self._score_cache[key] = breakdown
        entry_key = f"{document_key}|{breakdown.methodology_version}"
        self._score_history.setdefault(key, {})[entry_key] = self._summary(breakdown)

    @staticmethod
    def _summary(breakdown: ESGScoreBreakdownResponse) -> ESGIntegrityScoreResponse:
        return ESGIntegrityScoreResponse(
            **breakdown.model_dump(exclude={"dimensions", "claim_scores", "materiality_summary", "methodology_details"})
        )

    def get_company_score_breakdown(
        self, ticker: str, market: MarketIdentifier = MarketIdentifier.US_SEC
    ) -> ESGScoreBreakdownResponse:
        cached = self._score_cache.get(self._key(market, ticker))
        if cached is not None:
            return cached
        if market == MarketIdentifier.GH_GSE:
            return self.calculate_gse_score(ticker)
        return self.calculate_company_score(ticker)

    def get_company_score(
        self, ticker: str, market: MarketIdentifier = MarketIdentifier.US_SEC
    ) -> ESGIntegrityScoreResponse:
        return self._summary(self.get_company_score_breakdown(ticker, market))

    def get_company_score_history(
        self, ticker: str, market: MarketIdentifier = MarketIdentifier.US_SEC
    ) -> ESGScoreHistoryResponse:
        """Return only assessments actually computed in this process. Never fabricates history."""
        clean = (
            normalize_gse_ticker(ticker)
            if market == MarketIdentifier.GH_GSE
            else normalize_and_validate_ticker(ticker)
        )
        key = self._key(market, clean)
        entries = sorted(
            self._score_history.get(key, {}).values(),
            key=lambda e: (e.reporting_period or "", e.assessment_timestamp),
        )
        return ESGScoreHistoryResponse(
            company_name=entries[-1].company_name if entries else clean,
            ticker=clean,
            market=market,
            total_records=len(entries),
            history=entries,
            note=(
                "History contains only assessments computed by this server process (in-memory; no database in "
                "this phase). It is cleared on restart. One entry is kept per distinct source document and "
                "methodology version. No historical scores are estimated or fabricated."
            ),
        )


_scoring_service_instance: Optional[ScoringService] = None


def get_scoring_service() -> ScoringService:
    """Return a singleton instance of ScoringService."""
    global _scoring_service_instance
    if _scoring_service_instance is None:
        _scoring_service_instance = ScoringService()
    return _scoring_service_instance
