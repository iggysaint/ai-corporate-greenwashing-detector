"""ESG Integrity Scoring Service.

Responsible for deterministic synthesis, calculation, and explanation of ESG Integrity Scores
evaluating corporate sustainability disclosures against retrieved regulatory evidence.

IMPORTANT DISCLAIMER:
    The ESG Integrity Score evaluates ONLY the credibility and evidence substantiation
    of a company's disclosed sustainability claims based on retrieved corporate filings
    and disclosure documents.
    It does NOT:
    - Measure the company's entire environmental or social impact.
    - Serve as a comprehensive ESG performance rating.
    - Make legal determinations regarding greenwashing or fraud.
    - Substitute for an independent ESG audit.
"""

from collections import defaultdict
from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.models.claim import ClaimCategoryGroup, ClaimType
from app.models.company import Company
from app.models.evaluation import (
    AssessmentCategory,
    ClaimEvaluation,
    CompanyEvaluationResponse,
    EvaluationConfidence,
    EvaluationSummary,
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
from app.services.gse_service import GHANA_ESG_SECTORS, GSEService, get_gse_service
from app.services.llm_service import LLMService, get_llm_service
from app.services.sec_service import normalize_and_validate_ticker
from app.utils.config import Settings, get_settings
from app.utils.exceptions import CompanyNotFoundError, InsufficientDataError

logger = logging.getLogger(__name__)

# Base integrity scores by evaluation assessment category
BASE_ASSESSMENT_SCORES: Dict[AssessmentCategory, float] = {
    AssessmentCategory.SUPPORTED: 100.0,
    AssessmentCategory.PARTIALLY_SUPPORTED: 60.0,
    AssessmentCategory.UNSUBSTANTIATED: 25.0,
    AssessmentCategory.INCONSISTENT: 0.0,
    # INSUFFICIENT_EVIDENCE is excluded from the claim-level integrity average
    # and penalizes the evidence_coverage metric instead.
}

# Base materiality weights by claim type
CLAIM_TYPE_MATERIALITY: Dict[str, float] = {
    ClaimType.ACHIEVEMENT.value: 1.5,
    ClaimType.TARGET.value: 1.3,
    ClaimType.CURRENT_STATE.value: 1.2,
    ClaimType.POLICY.value: 0.9,
    ClaimType.GENERAL.value: 0.6,
}

# Regex for detecting quantitative specificity (numbers, %, $, units, explicit years)
QUANTITATIVE_PATTERN = re.compile(
    r"(?:\b\d+(?:\.\d+)?%|\$\s*\d+|\b\d{4}\b|\b\d+(?:\.\d+)?\s*(?:metric\s+tons|ghg|mwh|gwh|kwh|litres|gallons|tons|employees|workers|directors)\b)",
    re.I,
)

# High-priority materiality categories by sector keywords for US SEC SIC and GSE sectors
SECTOR_MATERIALITY_THEMES: Dict[str, List[str]] = {
    # Technology / Electronics (e.g. Apple, Google, Scancom)
    "telecommunications": ["energy", "renewable_energy", "carbon", "emissions", "diversity", "inclusion", "e-waste", "digital inclusion", "supply_chain", "compliance"],
    "technology": ["energy", "renewable_energy", "carbon", "emissions", "diversity", "inclusion", "e-waste", "supply_chain", "ethics", "compliance"],
    "electronic computers": ["energy", "renewable_energy", "carbon", "emissions", "diversity", "inclusion", "e-waste", "supply_chain"],
    # Mining / Extractives (e.g. AngloGold Ashanti)
    "mining": ["tailings", "water", "galamsey", "mineral", "pollution", "waste", "carbon", "emissions", "health_and_safety", "community", "environmental_management"],
    # Financial / Banking (e.g. GCB)
    "banking": ["financial inclusion", "microfinance", "mobile money", "governance", "ethics", "compliance", "transparency", "risk_management", "anti-corruption"],
    "financial services": ["financial inclusion", "governance", "ethics", "compliance", "transparency", "risk_management"],
    # Agriculture / Food (e.g. Unilever)
    "agriculture": ["deforestation", "cocoa", "palm oil", "water", "waste", "packaging", "supply_chain", "smallholder", "labor", "human_rights"],
    "consumer goods": ["packaging", "waste", "recycling", "plastics", "water", "supply_chain", "energy", "diversity"],
    # Manufacturing
    "manufacturing": ["effluent", "industrial waste", "waste", "emissions", "carbon", "energy", "health_and_safety", "labor"],
    # Oil & Gas
    "oil_and_gas": ["oil spill", "gas flaring", "carbon", "emissions", "pollution", "offshore", "health_and_safety", "environmental_management"],
}


class ScoringService:
    """Deterministic and explainable ESG Integrity Scoring Service."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        llm_service: Optional[LLMService] = None,
        gse_service: Optional[GSEService] = None,
    ):
        """Initialize the scoring service."""
        self.settings = settings or get_settings()
        self._llm_service = llm_service
        self._gse_service = gse_service

        # In-memory score storage for caching and history retrieval (no DB required)
        self._score_cache: Dict[str, ESGScoreBreakdownResponse] = {}
        self._score_history: Dict[str, List[ESGIntegrityScoreResponse]] = defaultdict(list)

    @property
    def llm_service(self) -> LLMService:
        """Lazily initialize LLMService singleton."""
        if self._llm_service is None:
            self._llm_service = get_llm_service()
        return self._llm_service

    @property
    def gse_service(self) -> GSEService:
        """Lazily initialize GSEService singleton."""
        if self._gse_service is None:
            self._gse_service = get_gse_service()
        return self._gse_service

    def clear_cache(self) -> None:
        """Clear all in-memory scoring caches and history."""
        self._score_cache.clear()
        self._score_history.clear()

    # ─────────────────────────────────────────────────────────
    # Core Pure Scoring Calculation Engine
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
        """Pure calculation engine that computes deterministic ESG Integrity Scores.

        Takes structured evaluations and disclosure metadata and computes:
        1. Claim-level integrity scores and materiality weights.
        2. Pillar-by-pillar dimensional scores (Environmental, Social, Governance).
        3. Overall materiality-weighted ESG Integrity Score.
        4. Evidence coverage and analytical confidence rating.
        5. Explainable positive factors and concerns.
        """
        source_refs = source_document_references or []
        methodology_version = self.settings.SCORING_METHODOLOGY_VERSION

        # Normalize sector/industry context for materiality assessment
        sector_key = (sector or industry or "").lower()

        # Step 1: Claim-level scoring and classification
        claim_details: List[ClaimScoreDetail] = []
        assessable_claims: List[ClaimScoreDetail] = []

        supported_count = 0
        partially_supported_count = 0
        inconsistent_count = 0
        unsubstantiated_count = 0
        insufficient_evidence_count = 0

        for ev in evaluations:
            # Assessment counts
            if ev.assessment == AssessmentCategory.SUPPORTED:
                supported_count += 1
            elif ev.assessment == AssessmentCategory.PARTIALLY_SUPPORTED:
                partially_supported_count += 1
            elif ev.assessment == AssessmentCategory.INCONSISTENT:
                inconsistent_count += 1
            elif ev.assessment == AssessmentCategory.UNSUBSTANTIATED:
                unsubstantiated_count += 1
            elif ev.assessment == AssessmentCategory.INSUFFICIENT_EVIDENCE:
                insufficient_evidence_count += 1

            # Base score
            base_score = BASE_ASSESSMENT_SCORES.get(ev.assessment, 0.0)

            # Specificity & quantification check
            is_quantified = bool(QUANTITATIVE_PATTERN.search(ev.claim_text))

            # Sector priority match check
            sector_priority = self._check_sector_priority(ev, sector_key)

            # Materiality weight calculation
            type_weight = CLAIM_TYPE_MATERIALITY.get(ev.claim_type, 1.0)
            quant_multiplier = 1.2 if is_quantified else 1.0
            sector_multiplier = 1.3 if sector_priority else 1.0
            materiality_weight = round(type_weight * quant_multiplier * sector_multiplier, 3)

            # Evidence quality factor
            quality_factor = self._compute_evidence_quality_factor(ev)

            # Claim-level score calculation
            if ev.assessment == AssessmentCategory.INCONSISTENT:
                # Contradicted claims strictly score 0.0 with full materiality penalty
                claim_score = 0.0
            elif ev.assessment == AssessmentCategory.INSUFFICIENT_EVIDENCE:
                claim_score = 0.0
            else:
                claim_score = round(min(100.0, max(0.0, base_score * quality_factor)), 1)

            ref_ids = [ref.evidence_id for ref in ev.referenced_evidence]

            detail = ClaimScoreDetail(
                claim_id=ev.claim_id,
                evaluation_id=ev.evaluation_id,
                claim_text=ev.claim_text,
                claim_type=ev.claim_type,
                category=ev.category,
                category_group=ev.category_group,
                assessment=ev.assessment,
                base_score=base_score,
                evidence_quality_factor=quality_factor,
                claim_score=claim_score,
                materiality_weight=materiality_weight,
                is_quantified=is_quantified,
                sector_priority_match=sector_priority,
                referenced_evidence_ids=ref_ids,
                caveats_count=len(ev.caveats),
                reasoning=ev.reasoning,
            )
            claim_details.append(detail)

            # Non-insufficient evidence claims are assessable for the integrity score
            if ev.assessment != AssessmentCategory.INSUFFICIENT_EVIDENCE:
                assessable_claims.append(detail)

        total_assessed = len(evaluations)
        total_extracted = total_claims_extracted if total_claims_extracted > 0 else total_assessed

        # Step 2: Evidence Coverage Calculation
        if total_assessed > 0:
            evidence_coverage = round(
                ((total_assessed - insufficient_evidence_count) / total_assessed) * 100.0,
                1,
            )
        else:
            evidence_coverage = 0.0

        # Step 3: Dimensional Pillar Breakdown (Environmental, Social, Governance)
        pillar_groups = {
            ClaimCategoryGroup.ENVIRONMENTAL.value: self.settings.SCORE_WEIGHT_ENVIRONMENTAL,
            ClaimCategoryGroup.SOCIAL.value: self.settings.SCORE_WEIGHT_SOCIAL,
            ClaimCategoryGroup.GOVERNANCE.value: self.settings.SCORE_WEIGHT_GOVERNANCE,
        }

        dimensions: Dict[str, DimensionalScore] = {}
        for pillar_name, configured_weight in pillar_groups.items():
            dim_score = self._compute_dimensional_score(
                pillar_name=pillar_name,
                all_claims=claim_details,
                configured_weight=configured_weight,
            )
            dimensions[pillar_name] = dim_score

        # Step 4: Overall Score & Status Calculation
        if len(assessable_claims) == 0:
            overall_score: Optional[float] = None
            score_status = ScoreStatus.INSUFFICIENT_DATA
            confidence = ConfidenceLevel.INSUFFICIENT
        else:
            score_status = ScoreStatus.SCORED

            # Materiality-weighted score aggregation across all assessable claims
            total_weight = sum(c.materiality_weight for c in assessable_claims)
            if total_weight > 0:
                weighted_sum = sum(c.materiality_weight * c.claim_score for c in assessable_claims)
                overall_score = round(min(100.0, max(0.0, weighted_sum / total_weight)), 1)
            else:
                overall_score = 0.0

            # Confidence determination
            confidence = self._determine_confidence(
                assessable_count=len(assessable_claims),
                evidence_coverage=evidence_coverage,
                dimensions=dimensions,
            )

        # Step 5: Effective weights normalization across active dimensions
        active_pillars = [p for p in dimensions.values() if p.status == ScoreStatus.SCORED]
        sum_active_weights = sum(p.weight for p in active_pillars)
        for p in dimensions.values():
            if p.status == ScoreStatus.SCORED and sum_active_weights > 0:
                p.effective_weight = round(p.weight / sum_active_weights, 3)
            else:
                p.effective_weight = 0.0

        # Step 6: Identify Main Positive Factors and Main Concerns
        main_positives, main_concerns = self._generate_factors_and_concerns(
            claim_details=claim_details,
            dimensions=dimensions,
            evidence_coverage=evidence_coverage,
            overall_score=overall_score,
        )

        env_score = dimensions.get(ClaimCategoryGroup.ENVIRONMENTAL.value, None)
        soc_score = dimensions.get(ClaimCategoryGroup.SOCIAL.value, None)
        gov_score = dimensions.get(ClaimCategoryGroup.GOVERNANCE.value, None)

        response = ESGScoreBreakdownResponse(
            company_name=company_name,
            ticker=ticker,
            market=market,
            reporting_period=reporting_period,
            esg_integrity_score=overall_score,
            score_status=score_status,
            confidence=confidence,
            evidence_coverage=evidence_coverage,
            environmental_score=env_score.score if env_score else None,
            social_score=soc_score.score if soc_score else None,
            governance_score=gov_score.score if gov_score else None,
            total_claims_extracted=total_extracted,
            total_claims_assessed=total_assessed,
            supported_claims=supported_count,
            partially_supported_claims=partially_supported_count,
            inconsistent_claims=inconsistent_count,
            unsubstantiated_claims=unsubstantiated_count,
            insufficient_evidence_claims=insufficient_evidence_count,
            main_positive_factors=main_positives,
            main_concerns=main_concerns,
            methodology_version=methodology_version,
            assessment_timestamp=datetime.now(timezone.utc).isoformat(),
            source_document_references=source_refs,
            dimensions=dimensions,
            claim_scores=claim_details,
            materiality_summary={
                "sector": sector,
                "industry": industry,
                "sector_priority_matches_count": sum(1 for c in claim_details if c.sector_priority_match),
                "quantified_claims_count": sum(1 for c in claim_details if c.is_quantified),
                "base_materiality_weights": CLAIM_TYPE_MATERIALITY,
            },
            methodology_details={
                "version": methodology_version,
                "base_assessment_scores": {k.value: v for k, v in BASE_ASSESSMENT_SCORES.items()},
                "dimensional_base_weights": {
                    "environmental": self.settings.SCORE_WEIGHT_ENVIRONMENTAL,
                    "social": self.settings.SCORE_WEIGHT_SOCIAL,
                    "governance": self.settings.SCORE_WEIGHT_GOVERNANCE,
                },
                "confidence_thresholds": {
                    "high": ">= 6 assessable claims, >= 70% coverage, >= 2 dimensions scored",
                    "medium": ">= 3 assessable claims, >= 50% coverage",
                    "low": "< 3 assessable claims or < 50% coverage",
                },
            },
        )

        return response

    # ─────────────────────────────────────────────────────────
    # Public SEC & GSE Scoring Workflow Integration
    # ─────────────────────────────────────────────────────────

    def calculate_company_score(
        self,
        ticker: str,
    ) -> ESGScoreBreakdownResponse:
        """Calculate and return full ESG Integrity Score breakdown for a US SEC listed company."""
        clean_ticker = normalize_and_validate_ticker(ticker)

        # 1. Evaluate filings via Phase 6 LLMService
        eval_resp: CompanyEvaluationResponse = self.llm_service.evaluate_company_filing(clean_ticker)

        company = eval_resp.company
        source_refs = [
            f"SEC EDGAR Form {eval_resp.form_type} (Accession: {eval_resp.filing_accession_number}, Filing Date: {eval_resp.filing_date})",
        ]

        # 2. Compute deterministic score
        breakdown = self.calculate_score_from_evaluations(
            company_name=company.company_name,
            ticker=company.ticker,
            market=MarketIdentifier.US_SEC,
            evaluations=eval_resp.evaluations,
            total_claims_extracted=eval_resp.summary.total_claims_extracted,
            reporting_period=eval_resp.filing_date[:4] if eval_resp.filing_date else None,
            sector=company.sic_description,
            industry=company.sic,
            source_document_references=source_refs,
        )

        # 3. Cache results and record in history
        cache_key = f"sec_{clean_ticker}_{eval_resp.filing_accession_number}"
        self._score_cache[clean_ticker] = breakdown
        self._score_cache[cache_key] = breakdown
        self._record_history(clean_ticker, breakdown)

        return breakdown

    def calculate_gse_score(
        self,
        ticker: str,
        source_url: Optional[str] = None,
        source_type: DocumentSourceType = DocumentSourceType.ANNUAL_REPORT,
        reporting_period: Optional[str] = None,
    ) -> ESGScoreBreakdownResponse:
        """Calculate and return full ESG Integrity Score breakdown for a Ghana Stock Exchange listed company."""
        from app.services.gse_service import normalize_gse_ticker

        clean_ticker = normalize_gse_ticker(ticker)

        # 1. Analyze GSE document via Phase 7A GSEService
        gse_resp: GSEAnalysisResponse = self.gse_service.analyze_company_document(
            ticker=clean_ticker,
            source_url=source_url,
            source_type=source_type,
            reporting_period=reporting_period,
        )

        company: GSECompany = gse_resp.company
        doc = gse_resp.document
        source_refs = [
            f"Ghana Stock Exchange: {doc.title} ({doc.format.upper()}, Period: {doc.reporting_period or 'N/A'}, Doc ID: {doc.document_id})",
        ]
        if doc.source_url:
            source_refs.append(doc.source_url)

        # 2. Compute deterministic score
        breakdown = self.calculate_score_from_evaluations(
            company_name=company.company_name,
            ticker=company.ticker,
            market=MarketIdentifier.GH_GSE,
            evaluations=gse_resp.evaluations,
            total_claims_extracted=gse_resp.total_claims_extracted,
            reporting_period=doc.reporting_period,
            sector=company.sector,
            industry=company.industry,
            source_document_references=source_refs,
        )

        # 3. Cache results and record in history
        cache_key = f"gse_{clean_ticker}_{doc.document_id}"
        self._score_cache[clean_ticker] = breakdown
        self._score_cache[cache_key] = breakdown
        self._record_history(clean_ticker, breakdown)

        return breakdown

    def get_company_score(
        self,
        ticker: str,
        market: MarketIdentifier = MarketIdentifier.US_SEC,
    ) -> ESGIntegrityScoreResponse:
        """Retrieve the primary ESG Integrity Score response for a company (US or GSE)."""
        clean_ticker = ticker.strip().upper()
        if clean_ticker in self._score_cache:
            breakdown = self._score_cache[clean_ticker]
        else:
            if market == MarketIdentifier.GH_GSE:
                breakdown = self.calculate_gse_score(clean_ticker)
            else:
                breakdown = self.calculate_company_score(clean_ticker)

        return ESGIntegrityScoreResponse(**breakdown.model_dump(exclude={"dimensions", "claim_scores", "materiality_summary", "methodology_details"}))

    def get_company_score_breakdown(
        self,
        ticker: str,
        market: MarketIdentifier = MarketIdentifier.US_SEC,
    ) -> ESGScoreBreakdownResponse:
        """Retrieve the detailed ESG Integrity Score breakdown with all claim details and pillar metrics."""
        clean_ticker = ticker.strip().upper()
        if clean_ticker in self._score_cache:
            return self._score_cache[clean_ticker]

        if market == MarketIdentifier.GH_GSE:
            return self.calculate_gse_score(clean_ticker)
        return self.calculate_company_score(clean_ticker)

    def get_company_score_history(
        self,
        ticker: str,
        market: MarketIdentifier = MarketIdentifier.US_SEC,
    ) -> ESGScoreHistoryResponse:
        """Retrieve the recorded historical scores for a company."""
        clean_ticker = ticker.strip().upper()
        history_list = self._score_history.get(clean_ticker, [])

        company_name = clean_ticker
        if history_list:
            company_name = history_list[-1].company_name
        elif clean_ticker in self._score_cache:
            company_name = self._score_cache[clean_ticker].company_name

        return ESGScoreHistoryResponse(
            company_name=company_name,
            ticker=clean_ticker,
            market=market,
            total_records=len(history_list),
            history=history_list,
        )

    # ─────────────────────────────────────────────────────────
    # Calculation Helper Methods
    # ─────────────────────────────────────────────────────────

    def _compute_evidence_quality_factor(self, ev: ClaimEvaluation) -> float:
        """Calculate quality multiplier based on retrieval relevance, evaluation confidence, and caveats.

        Returns:
            Quality multiplier clamped strictly within [0.75, 1.15].
        """
        factor = 1.0

        # Confidence adjustment
        if ev.confidence == EvaluationConfidence.HIGH:
            factor += 0.05
        elif ev.confidence == EvaluationConfidence.LOW:
            factor -= 0.05

        # Evidence relevance adjustment
        if ev.referenced_evidence:
            avg_rel = sum(ref.relevance_score for ref in ev.referenced_evidence) / len(ev.referenced_evidence)
            if avg_rel >= 0.40:
                factor += 0.05
            elif avg_rel < 0.20:
                factor -= 0.05

        # Caveats deduction (max deduction -0.15)
        if ev.caveats:
            deduction = min(len(ev.caveats) * 0.05, 0.15)
            factor -= deduction

        return round(min(1.15, max(0.75, factor)), 2)

    def _check_sector_priority(self, ev: ClaimEvaluation, sector_key: str) -> bool:
        """Determine whether a claim's category aligns with the company's sector priorities."""
        if not sector_key:
            return False

        # Match against known sector themes
        for sector_name, themes in SECTOR_MATERIALITY_THEMES.items():
            if sector_name in sector_key:
                claim_cat = ev.category.lower()
                claim_text_lower = ev.claim_text.lower()
                if any(t in claim_cat or t in claim_text_lower for t in themes):
                    return True

        # Also check Ghana ESG sector taxonomy
        for sector_name, keywords in GHANA_ESG_SECTORS.items():
            if sector_name in sector_key:
                claim_text_lower = ev.claim_text.lower()
                if any(kw in claim_text_lower for kw in keywords):
                    return True

        return False

    def _compute_dimensional_score(
        self,
        pillar_name: str,
        all_claims: List[ClaimScoreDetail],
        configured_weight: float,
    ) -> DimensionalScore:
        """Calculate score and evidence metrics for a single ESG pillar."""
        pillar_claims = [c for c in all_claims if c.category_group.lower() == pillar_name.lower()]
        total_in_pillar = len(pillar_claims)

        supported = sum(1 for c in pillar_claims if c.assessment == AssessmentCategory.SUPPORTED)
        partially = sum(1 for c in pillar_claims if c.assessment == AssessmentCategory.PARTIALLY_SUPPORTED)
        inconsistent = sum(1 for c in pillar_claims if c.assessment == AssessmentCategory.INCONSISTENT)
        unsubstantiated = sum(1 for c in pillar_claims if c.assessment == AssessmentCategory.UNSUBSTANTIATED)
        insufficient = sum(1 for c in pillar_claims if c.assessment == AssessmentCategory.INSUFFICIENT_EVIDENCE)

        assessable = [c for c in pillar_claims if c.assessment != AssessmentCategory.INSUFFICIENT_EVIDENCE]

        if total_in_pillar > 0:
            coverage = round(((total_in_pillar - insufficient) / total_in_pillar) * 100.0, 1)
        else:
            coverage = 0.0

        key_factors: List[str] = []

        if len(assessable) == 0:
            return DimensionalScore(
                dimension=pillar_name,
                score=None,
                status=ScoreStatus.INSUFFICIENT_DATA,
                weight=configured_weight,
                effective_weight=0.0,
                claims_count=total_in_pillar,
                assessable_claims_count=0,
                supported_count=supported,
                partially_supported_count=partially,
                inconsistent_count=inconsistent,
                unsubstantiated_count=unsubstantiated,
                insufficient_evidence_count=insufficient,
                evidence_coverage=coverage,
                confidence=ConfidenceLevel.INSUFFICIENT,
                key_factors=["Insufficient disclosure data available to compute a reliable pillar score."],
            )

        # Materiality-weighted score for this pillar
        w_sum = sum(c.materiality_weight for c in assessable)
        if w_sum > 0:
            score = round(min(100.0, max(0.0, sum(c.materiality_weight * c.claim_score for c in assessable) / w_sum)), 1)
        else:
            score = 0.0

        # Factors
        if supported > 0:
            key_factors.append(f"{supported} claim(s) directly corroborated with affirmative disclosure evidence.")
        if partially > 0:
            key_factors.append(f"{partially} claim(s) partially supported with operational or scope caveats.")
        if inconsistent > 0:
            key_factors.append(f"CONCERN: {inconsistent} claim(s) contradicted by disclosed performance metrics.")
        if unsubstantiated > 0:
            key_factors.append(f"{unsubstantiated} claim(s) lack formal verification or targets in filing.")

        # Pillar confidence
        if len(assessable) >= 3 and coverage >= 70.0:
            dim_conf = ConfidenceLevel.HIGH
        elif len(assessable) >= 2 and coverage >= 50.0:
            dim_conf = ConfidenceLevel.MEDIUM
        else:
            dim_conf = ConfidenceLevel.LOW

        return DimensionalScore(
            dimension=pillar_name,
            score=score,
            status=ScoreStatus.SCORED,
            weight=configured_weight,
            effective_weight=configured_weight,
            claims_count=total_in_pillar,
            assessable_claims_count=len(assessable),
            supported_count=supported,
            partially_supported_count=partially,
            inconsistent_count=inconsistent,
            unsubstantiated_count=unsubstantiated,
            insufficient_evidence_count=insufficient,
            evidence_coverage=coverage,
            confidence=dim_conf,
            key_factors=key_factors,
        )

    def _determine_confidence(
        self,
        assessable_count: int,
        evidence_coverage: float,
        dimensions: Dict[str, DimensionalScore],
    ) -> ConfidenceLevel:
        """Determine analytical confidence level based on claim count, coverage, and pillar diversity."""
        if assessable_count == 0:
            return ConfidenceLevel.INSUFFICIENT

        # Small sample guard: fewer than 3 claims can never achieve HIGH confidence
        if assessable_count < 3:
            return ConfidenceLevel.LOW

        scored_dimensions = sum(1 for d in dimensions.values() if d.status == ScoreStatus.SCORED)

        if assessable_count >= 6 and evidence_coverage >= 70.0 and scored_dimensions >= 2:
            return ConfidenceLevel.HIGH

        if assessable_count >= 3 and evidence_coverage >= 50.0:
            return ConfidenceLevel.MEDIUM

        return ConfidenceLevel.LOW

    def _generate_factors_and_concerns(
        self,
        claim_details: List[ClaimScoreDetail],
        dimensions: Dict[str, DimensionalScore],
        evidence_coverage: float,
        overall_score: Optional[float],
    ) -> Tuple[List[str], List[str]]:
        """Generate human-readable analytical factors and concerns."""
        positives: List[str] = []
        concerns: List[str] = []

        # 1. Inspect supported claims
        supported_material = [c for c in claim_details if c.assessment == AssessmentCategory.SUPPORTED and c.materiality_weight >= 1.5]
        if supported_material:
            sample = supported_material[0]
            clean_text = sample.claim_text.replace("\n", " ").strip()
            if len(clean_text) > 90:
                clean_text = clean_text[:87] + "..."
            positives.append(f"Substantiated high-materiality {sample.category} claim: '{clean_text}'")

        # 2. Check strong dimensional scores
        for d in dimensions.values():
            if d.score is not None and d.score >= 75.0:
                positives.append(f"Strong disclosure integrity in {d.dimension.capitalize()} pillar (Score: {d.score}/100, {d.supported_count} supported claims).")

        # 3. High coverage
        if evidence_coverage >= 80.0:
            positives.append(f"High evidence coverage ({evidence_coverage}%): majority of sustainability claims are corroborated by filing disclosures.")

        if not positives:
            positives.append("Filing provides baseline sustainability disclosures for review.")

        # 4. Inconsistent claims (always top concern)
        inconsistent_claims = [c for c in claim_details if c.assessment == AssessmentCategory.INCONSISTENT]
        for inc in inconsistent_claims[:2]:
            clean_text = inc.claim_text.replace("\n", " ").strip()
            if len(clean_text) > 85:
                clean_text = clean_text[:82] + "..."
            concerns.append(f"CONTRADICTION: Disclosed filing data contradicts {inc.category} claim: '{clean_text}'")

        # 5. Unsubstantiated high-materiality claims
        unsubstantiated_targets = [c for c in claim_details if c.assessment == AssessmentCategory.UNSUBSTANTIATED and c.claim_type in {ClaimType.TARGET.value, ClaimType.ACHIEVEMENT.value}]
        if unsubstantiated_targets:
            sample = unsubstantiated_targets[0]
            clean_text = sample.claim_text.replace("\n", " ").strip()
            if len(clean_text) > 85:
                clean_text = clean_text[:82] + "..."
            concerns.append(f"UNSUBSTANTIATED: High-impact {sample.category} commitment lacks milestone targets or verification: '{clean_text}'")

        # 6. Low coverage
        if evidence_coverage < 50.0:
            concerns.append(f"Low evidence coverage ({evidence_coverage}%): significant proportion of claims lack corroborating evidence passages.")

        # 7. Unscored pillars
        unscored_pillars = [d.dimension.capitalize() for d in dimensions.values() if d.status == ScoreStatus.INSUFFICIENT_DATA]
        if unscored_pillars:
            concerns.append(f"Missing disclosure data in {', '.join(unscored_pillars)} pillar(s).")

        return positives, concerns

    def _record_history(self, ticker: str, breakdown: ESGScoreBreakdownResponse) -> None:
        """Append an evaluation result to the in-memory history cache."""
        summary_resp = ESGIntegrityScoreResponse(**breakdown.model_dump(exclude={"dimensions", "claim_scores", "materiality_summary", "methodology_details"}))
        self._score_history[ticker].append(summary_resp)


# Singleton instance
_scoring_service_instance: Optional[ScoringService] = None


def get_scoring_service() -> ScoringService:
    """Return a singleton instance of ScoringService."""
    global _scoring_service_instance
    if _scoring_service_instance is None:
        _scoring_service_instance = ScoringService()
    return _scoring_service_instance
