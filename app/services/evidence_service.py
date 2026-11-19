"""Evidence & Cross-Reference Engine Service.

This service retrieves structured evidence passages from SEC 10-K filings that are
relevant to extracted sustainability claims. It is a deterministic retrieval layer only.

IMPORTANT DISCLAIMER:
    This service does NOT determine whether a company is greenwashing, committing fraud,
    or making false statements. Evidence records represent retrieved filing content that
    may relate to a sustainability claim. Objective assessment is deferred to Phase 6
    LLM-based analysis.

Evidence Retrieval Pipeline:
    1. Resolve company and latest annual filing (via SECService).
    2. Retrieve and parse the 10-K document (via DocumentService).
    3. Extract sustainability claims (via ClaimsService).
    4. For each claim:
       a. Extract claim-specific search concepts (keywords, metric, years, units, values).
       b. Search every document section paragraph for concept overlap.
       c. Score each candidate passage using a transparent relevance formula.
       d. Filter passages below minimum relevance threshold.
       e. Classify the evidence relationship deterministically (conservative).
       f. Classify evidence type and strength.
       g. Deduplicate passages discovered through multiple concepts.
       h. Attach full source traceability.
    5. Return structured ClaimEvidenceResult records.

Relevance Score Formula (transparent, 0.0–1.0):
    score = (
        concept_overlap_ratio * 0.40   # fraction of claim concepts matched
        + metric_match_bonus   * 0.20   # claim metric found in passage
        + year_match_bonus     * 0.15   # claim target/baseline year found
        + value_match_bonus    * 0.15   # claim quantitative value found
        + section_bonus        * 0.10   # ESG-relevant section weighting
    )

This formula is deterministic and does not involve an LLM.
"""

import hashlib
import logging
import re
from typing import Dict, List, Optional, Set, Tuple

from app.models.claim import Claim
from app.models.company import Company
from app.models.document import Document, DocumentSection
from app.models.evidence import (
    ClaimEvidenceResult,
    CompanyEvidenceResponse,
    Evidence,
    EvidenceRelationship,
    EvidenceStrength,
    EvidenceSummaryResponse,
    EvidenceType,
)
from app.models.filing import SECFiling
from app.services.claims_service import ClaimsService, get_claims_service
from app.services.document_service import DocumentService, get_document_service
from app.services.sec_service import SECService, get_sec_service
from app.utils.config import Settings, get_settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────

# Minimum relevance score for a passage to qualify as evidence
MIN_RELEVANCE_THRESHOLD = 0.10

# Maximum evidence records to return per claim
MAX_EVIDENCE_PER_CLAIM = 10

# Maximum "best evidence" records in ClaimEvidenceResult
MAX_BEST_EVIDENCE = 3

# Minimum passage length (characters) to consider as evidence
MIN_PASSAGE_LENGTH = 40

# Section relevance weights: higher = more ESG-relevant sections
SECTION_RELEVANCE_WEIGHTS: Dict[str, float] = {
    "item_1": 0.8,        # Business
    "item_1a": 0.5,       # Risk Factors (useful context but often hedged)
    "item_1c": 0.7,       # Cybersecurity (limited ESG relevance)
    "item_7": 0.9,        # MD&A — highest for actual performance data
    "item_7a": 0.6,       # Market risk
    "item_8": 0.7,        # Financial Statements — may contain ESG metrics
    "item_9a": 0.6,       # Controls & Procedures
    "item_10": 0.8,       # Governance
    "item_11": 0.5,       # Executive Compensation
    "full_document": 0.5,
}
DEFAULT_SECTION_WEIGHT = 0.4

# Patterns indicating qualifying/conditional language in evidence
QUALIFYING_LANGUAGE_PATTERNS = [
    re.compile(r"\b(?:subject to|where feasible|where possible|where practicable|contingent (?:on|upon))\b", re.I),
    re.compile(r"\b(?:selected|limited|specific)\s+(?:facilities|locations|operations|markets|regions|suppliers|products)\b", re.I),
    re.compile(r"\b(?:partially|preliminary|unverified|unaudited)\b", re.I),
    re.compile(r"\b(?:depending (?:on|upon)|to the extent (?:feasible|practicable|possible))\b", re.I),
    re.compile(r"\b(?:exceptions?|excluding|excludes?|with the exception of)\b", re.I),
]

# Patterns indicating forward-looking target language (not achievement evidence)
TARGET_LANGUAGE_PATTERNS = [
    re.compile(r"\b(?:by\s+20[2-5][0-9]|through\s+20[2-5][0-9])\b", re.I),
    re.compile(r"\b(?:aim|aims|aiming|aspire|aspires|aspiring)\s+to\b", re.I),
    re.compile(r"\b(?:commit|commits|committed|commitment)\s+to\b", re.I),
    re.compile(r"\b(?:plan|plans|planning|intend|intends)\s+to\b", re.I),
    re.compile(r"\b(?:net[- ]zero|carbon[- ]neutral)\s+by\b", re.I),
    re.compile(r"\b(?:goal|goals|target|targets)\s+(?:of|to|for|is)\b", re.I),
]

# Patterns indicating realized past achievements (not just forward-looking targets)
ACHIEVEMENT_LANGUAGE_PATTERNS = [
    re.compile(r"\b(?:achieved|attained|reached|exceeded|surpassed|delivered)\b", re.I),
    re.compile(r"\b(?:reduced|decreased|declined|lowered|cut|eliminated)\b", re.I),
    re.compile(r"\b(?:increased|grew|improved|expanded)\b", re.I),
    re.compile(r"\b(?:in\s+(?:fiscal\s+)?20[0-2][0-9]|during\s+(?:fiscal\s+)?20[0-2][0-9])\b", re.I),
    re.compile(r"\b(?:completed|transitioned|implemented|deployed)\b", re.I),
    re.compile(r"\b(?:have\s+been|has\s+been|maintains?|maintained|sourced?|powered\s+by)\b", re.I),
    re.compile(r"\b(?:100%|net[- ]zero|carbon[- ]neutral)\b", re.I),
]

# Patterns indicating pure risk/uncertainty disclosures (not ESG performance evidence)
RISK_DISCLOSURE_PATTERNS = [
    re.compile(r"\b(?:could|may)\s+(?:materially\s+)?adversely\s+affect\b", re.I),
    re.compile(r"\b(?:there\s+can\s+be\s+no\s+assurance|no\s+guarantee)\b", re.I),
    re.compile(r"\b(?:forward-looking\s+statements|forward\s+looking\s+information)\b", re.I),
    re.compile(r"\b(?:risks?|uncertainties?)\s+(?:that\s+)?(?:could|may|might)\b", re.I),
    re.compile(r"\b(?:if|in\s+the\s+event\s+that)\s+(?:we|the\s+company)\s+(?:fail|are\s+unable)\b", re.I),
]

# Sentence-level split for evidence passage segmentation
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])(?<!\d\.)\s+(?=[A-Z0-9\"'])")


def _matches_term(term: str, text: str) -> bool:
    """Match term against text respecting word boundaries where appropriate.

    Applies boundary \b only if the term starts/ends with a word character,
    avoiding boundary-matching failures on symbols like '%'.
    """
    if not term:
        return False
    prefix = r"\b" if re.match(r"^\w", term) else ""
    suffix = r"\b" if re.search(r"\w$", term) else ""
    return bool(re.search(prefix + re.escape(term) + suffix, text, re.I))


# ─────────────────────────────────────────────────────────
# Concept Extraction Helpers
# ─────────────────────────────────────────────────────────

def _extract_claim_concepts(claim: Claim) -> Tuple[List[str], List[str]]:
    """Extract search concepts and keyword terms from a claim.

    Returns:
        Tuple of (concepts, terms) where:
          - concepts: high-level named concepts (metric, category, claim_type markers)
          - terms: individual lowercased tokens to search for
    """
    concepts: List[str] = []
    terms: Set[str] = set()

    # 1. Metric (most specific — highest priority)
    if claim.metric:
        concepts.append(claim.metric)
        for word in re.split(r"\s+", claim.metric):
            if len(word) > 3:
                terms.add(word.lower())

    # 2. Category concept
    if claim.category:
        cat_normalized = claim.category.replace("_", " ")
        concepts.append(cat_normalized)
        for word in cat_normalized.split():
            if len(word) > 3:
                terms.add(word.lower())

    # 3. Target value — e.g. "100%", "net zero"
    if claim.target_value:
        val_clean = claim.target_value.strip().lower()
        concepts.append(val_clean)
        terms.add(val_clean)

    # 4. Unit
    if claim.unit:
        terms.add(claim.unit.lower().replace("_", " "))

    # 5. Years
    if claim.target_year:
        terms.add(str(claim.target_year))
        concepts.append(f"target year {claim.target_year}")
    if claim.baseline_year:
        terms.add(str(claim.baseline_year))
        concepts.append(f"baseline year {claim.baseline_year}")

    # 6. Key tokens from claim text (skip stopwords and short tokens)
    STOPWORDS = {
        "the", "and", "or", "of", "to", "in", "a", "an", "is", "are", "was",
        "were", "has", "have", "had", "for", "on", "at", "by", "with", "that",
        "this", "it", "its", "our", "we", "be", "as", "from", "will", "not",
        "all", "any", "may", "can", "do", "does", "did", "which", "who", "how",
        "company", "companys", "business", "operations", "services", "financial",
        "condition", "results", "fiscal", "quarter", "annual", "report",
        "statement", "statements", "including", "information", "general",
        "certain", "approximately", "primarily", "substantially", "apple",
        "total", "other", "their", "there", "would", "could", "should", "been",
        "than", "more", "most", "into", "over", "also", "such", "under", "these",
        "while", "time", "date", "period", "years", "ended", "item", "table",
        "materially", "adversely", "affect", "affects", "affected", "price",
        "stock", "occur", "occurs", "occurred", "partner", "partners",
        "reputation", "relies",
    }
    for token in re.split(r"[\s\-–—,;:()\[\]\"'\.]+", claim.claim_text.lower()):
        token_clean = re.sub(r"[^a-z0-9%]+", "", token)
        if len(token_clean) > 3 and token_clean not in STOPWORDS:
            terms.add(token_clean)

    return concepts, sorted(terms)


def _extract_percentage(text: str) -> Optional[float]:
    """Extract a numeric percentage value from text, or None."""
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:%|percent)\b", text, re.I)
    if not m:
        m = re.search(r"\b(\d+(?:\.\d+)?)\s*%", text)
    if m:
        return float(m.group(1))
    return None


def _extract_years(text: str) -> Set[int]:
    """Extract all 4-digit years (2000–2059) from text."""
    return {int(y) for y in re.findall(r"\b(20[0-5][0-9])\b", text)}


# ─────────────────────────────────────────────────────────
# Evidence Service
# ─────────────────────────────────────────────────────────

class EvidenceService:
    """Deterministic Evidence & Cross-Reference Engine.

    Retrieves evidence passages from SEC 10-K filings that are relevant to
    extracted sustainability claims. Does not use an LLM. Does not produce
    ESG scores or greenwashing determinations.

    All evidence records preserve complete source traceability to the
    original SEC EDGAR filing, section, and approximate character position.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        sec_service: Optional[SECService] = None,
        doc_service: Optional[DocumentService] = None,
        claims_service: Optional[ClaimsService] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sec_service = sec_service or get_sec_service()
        self.doc_service = doc_service or get_document_service()
        self.claims_service = claims_service or get_claims_service()

        # In-memory cache: accession_number -> List[ClaimEvidenceResult]
        self._evidence_cache: Dict[str, List[ClaimEvidenceResult]] = {}

    def clear_cache(self) -> None:
        """Clear the in-memory evidence cache."""
        self._evidence_cache.clear()

    # ──────────────────────────────────────────────────────
    # Evidence ID Generation
    # ──────────────────────────────────────────────────────

    @staticmethod
    def generate_evidence_id(claim_id: str, evidence_text: str, section_id: str) -> str:
        """Generate a stable, deterministic evidence ID.

        The ID is derived from the claim ID, normalized evidence text, and section,
        ensuring the same passage found for the same claim always produces the same ID.
        """
        norm = re.sub(r"[^a-z0-9]", "", evidence_text[:200].lower())
        seed = f"{claim_id}_{section_id}_{norm}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
        return f"ev_{digest}"

    # ──────────────────────────────────────────────────────
    # Relevance Scoring
    # ──────────────────────────────────────────────────────

    def _score_passage(
        self,
        passage_text: str,
        claim: Claim,
        concepts: List[str],
        terms: List[str],
        section_id: str,
    ) -> Tuple[float, List[str], List[str]]:
        """Score a passage for relevance to a claim.

        Returns:
            Tuple of (relevance_score, matched_concepts, matched_terms)

        Relevance Score Formula (transparent):
            score = (
                concept_overlap_ratio * 0.40
                + metric_match_bonus   * 0.20
                + year_match_bonus     * 0.15
                + value_match_bonus    * 0.15
                + section_bonus        * 0.10
            )

        All components are capped at their maximum weights so the total is always ≤ 1.0.
        """
        passage_lower = passage_text.lower()
        matched_terms_found: List[str] = []
        matched_concepts_found: List[str] = []

        # 1. Term overlap
        for term in terms:
            if _matches_term(term, passage_text):
                matched_terms_found.append(term)

        # 2. Concept overlap ratio (0.0–0.40)
        # Combines high-level concepts and specific key term overlap
        term_ratio = len(matched_terms_found) / max(len(terms), 1)

        if concepts:
            concept_hits = 0
            for concept in concepts:
                concept_words = [w for w in concept.lower().split() if len(w) > 2]
                if concept_words and all(
                    _matches_term(w, passage_lower)
                    for w in concept_words
                ):
                    concept_hits += 1
                    matched_concepts_found.append(concept)
            concept_ratio = concept_hits / len(concepts)
            effective_overlap = max(concept_ratio, term_ratio)
        else:
            effective_overlap = term_ratio

        concept_component = min(effective_overlap, 1.0) * 0.40

        # 3. Metric match bonus (0.0–0.20)
        metric_bonus = 0.0
        if claim.metric:
            metric_words = [w for w in claim.metric.lower().split() if len(w) > 2]
            if metric_words and all(
                _matches_term(w, passage_lower)
                for w in metric_words
            ):
                metric_bonus = 0.20

        # 4. Year match bonus (0.0–0.15)
        year_bonus = 0.0
        passage_years = _extract_years(passage_text)
        if claim.target_year and claim.target_year in passage_years:
            year_bonus += 0.10
        if claim.baseline_year and claim.baseline_year in passage_years:
            year_bonus += 0.05
        year_bonus = min(year_bonus, 0.15)

        # 5. Quantitative value match bonus (0.0–0.15)
        value_bonus = 0.0
        if claim.target_value:
            # Exact value match
            if claim.target_value.lower() in passage_lower:
                value_bonus = 0.15
            else:
                # Fuzzy percentage comparison: within 5 percentage points
                claim_pct = _extract_percentage(claim.target_value)
                passage_pct = _extract_percentage(passage_text)
                if claim_pct is not None and passage_pct is not None:
                    if abs(claim_pct - passage_pct) <= 5.0:
                        value_bonus = 0.10
                    elif abs(claim_pct - passage_pct) <= 15.0:
                        value_bonus = 0.05

        # 6. Section relevance bonus (0.0–0.10)
        section_weight = SECTION_RELEVANCE_WEIGHTS.get(section_id, DEFAULT_SECTION_WEIGHT)
        section_bonus = section_weight * 0.10

        total_score = concept_component + metric_bonus + year_bonus + value_bonus + section_bonus
        total_score = round(min(max(total_score, 0.0), 1.0), 4)

        return total_score, matched_concepts_found, matched_terms_found

    # ──────────────────────────────────────────────────────
    # Evidence Type Classification
    # ──────────────────────────────────────────────────────

    @staticmethod
    def _classify_evidence_type(passage_text: str) -> EvidenceType:
        """Classify the type of an evidence passage deterministically."""
        text_lower = passage_text.lower()

        # Quantitative: contains measurable numbers, %, metric tons, etc.
        if re.search(r"\b\d+(?:\.\d+)?\s*(?:%|percent|metric\s+tons?|mwh|gwh|gallons?|liters?)\b", passage_text, re.I):
            return EvidenceType.QUANTITATIVE

        # Financial: contains dollar figures or financial terminology
        if re.search(r"\$\s*\d+|billion|million|revenue|cost|expenditure|capex", text_lower):
            return EvidenceType.FINANCIAL

        # Target: forward-looking commitment language
        if any(p.search(passage_text) for p in TARGET_LANGUAGE_PATTERNS):
            return EvidenceType.TARGET

        # Achievement: past tense performance
        if any(p.search(passage_text) for p in ACHIEVEMENT_LANGUAGE_PATTERNS):
            return EvidenceType.ACHIEVEMENT

        # Policy: framework/standard/code language
        if re.search(
            r"\b(?:policy|code\s+of\s+conduct|standard|framework|program|protocol)\b",
            text_lower,
        ):
            return EvidenceType.POLICY

        # Risk: risk/uncertainty language
        if any(p.search(passage_text) for p in RISK_DISCLOSURE_PATTERNS):
            return EvidenceType.RISK

        # Operational: processes, practices, operations
        if re.search(r"\b(?:operations?|practices?|processes?|activities|facilities)\b", text_lower):
            return EvidenceType.OPERATIONAL

        # Baseline: reference to prior period
        if re.search(r"\b(?:baseline|base\s+year|prior\s+year|compared\s+(?:to|with))\b", text_lower):
            return EvidenceType.BASELINE

        # Qualitative or disclosure
        if len(passage_text.split()) >= 10:
            return EvidenceType.QUALITATIVE

        return EvidenceType.DISCLOSURE

    # ──────────────────────────────────────────────────────
    # Relationship Classification
    # ──────────────────────────────────────────────────────

    def _classify_relationship(
        self,
        claim: Claim,
        passage_text: str,
        relevance_score: float,
        matched_terms: List[str],
        section_id: str = "",
    ) -> EvidenceRelationship:
        """Classify the relationship between a claim and an evidence passage.

        This classification is conservative and deterministic. When the relationship
        cannot be determined reliably, we default to CONTEXTUAL rather than making
        an aggressive conclusion.

        IMPORTANT: This does not determine whether a company is greenwashing.
        """
        if relevance_score < MIN_RELEVANCE_THRESHOLD or not matched_terms:
            return EvidenceRelationship.INSUFFICIENT_EVIDENCE

        text_lower = passage_text.lower()

        # Detect pure risk statements and risk factor sections
        # Core Rule: Risk disclaimers are contextual evidence only, never supporting or contradictory.
        is_risk_statement = any(p.search(passage_text) for p in RISK_DISCLOSURE_PATTERNS)
        is_risk_section = section_id.lower() == "item_1a"

        # Detect qualifying language
        has_qualifying_language = any(p.search(passage_text) for p in QUALIFYING_LANGUAGE_PATTERNS)

        # Detect target vs achievement language in evidence passage
        has_target_language = any(p.search(passage_text) for p in TARGET_LANGUAGE_PATTERNS)
        has_achievement_language = any(p.search(passage_text) for p in ACHIEVEMENT_LANGUAGE_PATTERNS)

        # ── RISK STATEMENTS & ITEM 1A (Risk Factors) ────────────────
        # Risk factors provide context or condition commitments, never direct performance corroboration or contradiction
        if is_risk_statement or is_risk_section:
            if has_qualifying_language:
                return EvidenceRelationship.QUALIFYING
            return EvidenceRelationship.CONTEXTUAL

        # ── CONTRADICTORY detection (conservative) ──────────────────
        # Only flag contradictory if:
        # 1. Quantitative claim with specific value and metric
        # 2. Evidence contains clearly different value for SAME metric
        # 3. Not differing reporting periods (same period or overlapping years)
        if (
            claim.target_value
            and claim.metric
        ):
            claim_pct = _extract_percentage(claim.target_value)
            evidence_pct = _extract_percentage(passage_text)

            if (
                claim_pct is not None
                and evidence_pct is not None
                and abs(claim_pct - evidence_pct) > 20.0
            ):
                # Guard against differing reporting years
                passage_years = _extract_years(passage_text)
                claim_years = {y for y in [claim.target_year, claim.baseline_year] if y is not None}
                years_conflict = bool(claim_years and passage_years and not (claim_years & passage_years))

                if not years_conflict:
                    claim_metric_words = [w for w in (claim.metric or "").lower().split() if len(w) > 3]
                    if claim_metric_words and all(
                        _matches_term(w, text_lower)
                        for w in claim_metric_words
                    ):
                        if (
                            claim.claim_type in ("achievement", "current_state")
                            and has_achievement_language
                            and not has_target_language
                        ):
                            return EvidenceRelationship.CONTRADICTORY

        # ── SUPPORTING / QUALIFYING detection ─────────────────────────
        # Conservative requirement: reasonable relevance + metric presence + alignment
        if relevance_score >= 0.30 and matched_terms:
            claim_metric_words = [w for w in (claim.metric or "").lower().split() if len(w) > 3]
            metric_present = not claim_metric_words or all(
                _matches_term(w, text_lower)
                for w in claim_metric_words
            )

            if metric_present:
                # Direct quantitative match for any claim
                if claim.target_value and claim.target_value.lower() in text_lower:
                    if has_qualifying_language:
                        return EvidenceRelationship.QUALIFYING
                    return EvidenceRelationship.SUPPORTING

                # Target claim supported by target commitment in filing
                if claim.claim_type == "target" and has_target_language:
                    if has_qualifying_language:
                        return EvidenceRelationship.QUALIFYING
                    return EvidenceRelationship.SUPPORTING

                # Achievement / current state claim supported by achievement or quantitative evidence
                if claim.claim_type in ("achievement", "current_state") and (
                    has_achievement_language or (claim.target_value and claim.target_value.lower() in text_lower)
                ):
                    if has_qualifying_language:
                        return EvidenceRelationship.QUALIFYING
                    return EvidenceRelationship.SUPPORTING

                # Policy claim supported by governance/policy text
                if claim.claim_type == "policy":
                    if re.search(
                        r"\b(?:policy|code\s+of\s+conduct|standard|framework|program|protocol)\b",
                        text_lower,
                    ):
                        if has_qualifying_language:
                            return EvidenceRelationship.QUALIFYING
                        return EvidenceRelationship.SUPPORTING

        # ── QUALIFYING detection (when not directly supporting) ─────────
        if has_qualifying_language:
            if claim.claim_type in ("target", "achievement", "current_state"):
                return EvidenceRelationship.QUALIFYING

        # ── Default: CONTEXTUAL ────────────────────────────────────
        return EvidenceRelationship.CONTEXTUAL

    # ──────────────────────────────────────────────────────
    # Evidence Strength Classification
    # ──────────────────────────────────────────────────────

    @staticmethod
    def _classify_strength(
        relevance_score: float,
        evidence_type: EvidenceType,
        relationship: EvidenceRelationship,
        has_metric_match: bool,
        has_year_match: bool,
        has_value_match: bool,
    ) -> EvidenceStrength:
        """Classify deterministic evidence strength.

        STRONG: Direct quantitative disclosure matching the claim's metric + relevant period.
        MODERATE: Relevant disclosure lacking one key component.
        WEAK: General contextual information.

        This is NOT a judgment of claim truthfulness.
        """
        if relationship == EvidenceRelationship.INSUFFICIENT_EVIDENCE:
            return EvidenceStrength.WEAK

        if (
            evidence_type == EvidenceType.QUANTITATIVE
            and has_metric_match
            and (has_year_match or has_value_match)
            and relevance_score >= 0.40
        ):
            return EvidenceStrength.STRONG

        if evidence_type in (EvidenceType.QUANTITATIVE, EvidenceType.ACHIEVEMENT, EvidenceType.TARGET):
            if has_metric_match or has_value_match:
                return EvidenceStrength.MODERATE

        if relevance_score >= 0.30 and has_metric_match:
            return EvidenceStrength.MODERATE

        return EvidenceStrength.WEAK

    # ──────────────────────────────────────────────────────
    # Core Evidence Search for One Claim
    # ──────────────────────────────────────────────────────

    def _search_evidence_for_claim(
        self,
        claim: Claim,
        document: Document,
        filing: SECFiling,
    ) -> List[Evidence]:
        """Search the document for passages relevant to a single claim.

        Returns a deduplicated, relevance-ranked list of Evidence records.
        """
        concepts, terms = _extract_claim_concepts(claim)

        if not terms and not concepts:
            logger.debug("No extractable concepts for claim %s — returning empty", claim.claim_id)
            return []

        # Track seen normalized evidence texts to deduplicate
        seen_evidence: Dict[str, int] = {}  # norm_text -> index in candidate_evidence
        candidate_evidence: List[Evidence] = []

        sections_to_search = document.sections
        if not sections_to_search:
            sections_to_search = [
                DocumentSection(
                    section_id="full_document",
                    section_title="Full Document",
                    section_type="other",
                    text=document.text,
                    start_position=0,
                    end_position=len(document.text),
                    word_count=document.word_count,
                )
            ]

        for section in sections_to_search:
            # Search at paragraph level within each section
            # Supports both double-newline and single-newline separated paragraphs
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\r?\n", section.text) if p.strip()]
            section_offset = 0

            for para_clean in paragraphs:
                para_len = len(para_clean) + 1

                if len(para_clean) < MIN_PASSAGE_LENGTH:
                    section_offset += para_len
                    continue

                # Quick pre-filter: at least one term must appear in the paragraph
                para_lower = para_clean.lower()
                if not any(term in para_lower for term in terms):
                    section_offset += para_len
                    continue

                # Score the passage
                score, matched_concepts, matched_terms_found = self._score_passage(
                    passage_text=para_clean,
                    claim=claim,
                    concepts=concepts,
                    terms=terms,
                    section_id=section.section_id,
                )

                # Substantive match guard: require at least 1 concept match OR >= 2 distinct matched terms,
                # or a specific metric/quantitative match. Lone single terms in unrelated paragraphs are ignored.
                has_substantive_match = (
                    bool(matched_concepts)
                    or len(matched_terms_found) >= 2
                    or (claim.metric and claim.metric.lower() in para_lower)
                    or (claim.target_value and claim.target_value.lower() in para_lower)
                )

                if score < MIN_RELEVANCE_THRESHOLD or not has_substantive_match:
                    section_offset += para_len
                    continue

                # Deduplication: normalize text for fingerprint
                norm_text = re.sub(r"[^a-z0-9]", "", para_clean[:200].lower())

                if norm_text in seen_evidence:
                    # Merge matched concepts/terms into existing evidence record
                    existing_idx = seen_evidence[norm_text]
                    existing = candidate_evidence[existing_idx]
                    merged_concepts = list(set(existing.matched_concepts) | set(matched_concepts))
                    merged_terms = list(set(existing.matched_terms) | set(matched_terms_found))
                    # Rebuild with merged data (Pydantic model is immutable — create new)
                    candidate_evidence[existing_idx] = existing.model_copy(
                        update={
                            "matched_concepts": merged_concepts,
                            "matched_terms": merged_terms,
                            "relevance_score": max(existing.relevance_score, score),
                        }
                    )
                    section_offset += para_len
                    continue

                # Classify evidence type
                evidence_type = self._classify_evidence_type(para_clean)

                # Classify relationship
                relationship = self._classify_relationship(
                    claim=claim,
                    passage_text=para_clean,
                    relevance_score=score,
                    matched_terms=matched_terms_found,
                    section_id=section.section_id,
                )

                # Determine helper booleans for strength classification
                passage_years = _extract_years(para_clean)
                has_year_match = bool(
                    (claim.target_year and claim.target_year in passage_years)
                    or (claim.baseline_year and claim.baseline_year in passage_years)
                )
                has_value_match = bool(
                    claim.target_value and claim.target_value.lower() in para_lower
                )
                claim_metric_words = [w for w in (claim.metric or "").lower().split() if len(w) > 3]
                has_metric_match = bool(claim_metric_words) and all(
                    re.search(r"\b" + re.escape(w) + r"\b", para_lower)
                    for w in claim_metric_words
                )

                strength = self._classify_strength(
                    relevance_score=score,
                    evidence_type=evidence_type,
                    relationship=relationship,
                    has_metric_match=has_metric_match,
                    has_year_match=has_year_match,
                    has_value_match=has_value_match,
                )

                # Confidence
                confidence = "high" if score >= 0.50 else ("medium" if score >= 0.25 else "low")

                # Truncate very long passages
                evidence_text = (
                    para_clean if len(para_clean) <= 800 else para_clean[:800] + "... [truncated]"
                )

                evidence_id = self.generate_evidence_id(
                    claim_id=claim.claim_id,
                    evidence_text=para_clean,
                    section_id=section.section_id,
                )

                evidence = Evidence(
                    evidence_id=evidence_id,
                    claim_id=claim.claim_id,
                    company_ticker=claim.company_ticker,
                    company_name=claim.company_name,
                    evidence_text=evidence_text,
                    evidence_type=evidence_type.value,
                    relationship=relationship.value,
                    source_type="sec_10k",
                    source_title=document.title or f"{filing.form_type} Annual Report",
                    source_url=filing.filing_url,
                    filing_accession_number=filing.accession_number,
                    filing_date=filing.filing_date,
                    report_date=filing.report_date,
                    section_id=section.section_id,
                    section_title=section.section_title,
                    source_location=section.section_title,
                    approximate_position=section.start_position + section_offset,
                    matched_concepts=matched_concepts,
                    matched_terms=matched_terms_found,
                    relevance_score=score,
                    evidence_strength=strength.value,
                    extraction_method="deterministic",
                    confidence=confidence,
                )

                seen_evidence[norm_text] = len(candidate_evidence)
                candidate_evidence.append(evidence)

                section_offset += para_len

        # Sort by relevance score descending and cap at MAX_EVIDENCE_PER_CLAIM
        candidate_evidence.sort(key=lambda e: e.relevance_score, reverse=True)
        return candidate_evidence[:MAX_EVIDENCE_PER_CLAIM]

    # ──────────────────────────────────────────────────────
    # Strongest Relationship Helper
    # ──────────────────────────────────────────────────────

    @staticmethod
    def _determine_strongest_relationship(evidence_list: List[Evidence]) -> str:
        """Determine the predominant retrieval relationship among evidence records.

        Priority order: contradictory > supporting > qualifying > contextual > insufficient_evidence

        IMPORTANT: This is a retrieval summary only. It does NOT constitute a
        greenwashing determination or legal judgment.
        """
        if not evidence_list:
            return EvidenceRelationship.INSUFFICIENT_EVIDENCE.value

        rel_counts: Dict[str, int] = {}
        for ev in evidence_list:
            rel_counts[ev.relationship] = rel_counts.get(ev.relationship, 0) + 1

        # Priority-based selection — preserve conflicts in individual records
        for rel in (
            EvidenceRelationship.CONTRADICTORY,
            EvidenceRelationship.SUPPORTING,
            EvidenceRelationship.QUALIFYING,
            EvidenceRelationship.CONTEXTUAL,
        ):
            if rel.value in rel_counts:
                return rel.value

        return EvidenceRelationship.INSUFFICIENT_EVIDENCE.value

    # ──────────────────────────────────────────────────────
    # Overall Retrieval Confidence Helper
    # ──────────────────────────────────────────────────────

    @staticmethod
    def _overall_retrieval_confidence(evidence_list: List[Evidence]) -> str:
        """Assess overall retrieval confidence from evidence quality."""
        if not evidence_list:
            return "insufficient"

        strong_count = sum(1 for e in evidence_list if e.evidence_strength == EvidenceStrength.STRONG.value)
        moderate_count = sum(1 for e in evidence_list if e.evidence_strength == EvidenceStrength.MODERATE.value)
        avg_score = sum(e.relevance_score for e in evidence_list) / len(evidence_list)

        if strong_count >= 1 and avg_score >= 0.50:
            return "high"
        if moderate_count >= 1 or avg_score >= 0.30:
            return "medium"
        return "low"

    # ──────────────────────────────────────────────────────
    # Public API Methods
    # ──────────────────────────────────────────────────────

    def get_company_evidence(
        self,
        ticker: str,
        category: Optional[str] = None,
        claim_type: Optional[str] = None,
        relationship: Optional[str] = None,
        minimum_relevance: float = 0.0,
        limit: int = 50,
    ) -> CompanyEvidenceResponse:
        """Retrieve evidence for all sustainability claims of the latest 10-K.

        Args:
            ticker: Company stock ticker symbol.
            category: Optional ESG category filter.
            claim_type: Optional claim type filter.
            relationship: Optional relationship filter (supporting, contradictory, etc.).
            minimum_relevance: Minimum relevance score threshold (0.0–1.0).
            limit: Maximum number of ClaimEvidenceResult records to return.

        Returns:
            CompanyEvidenceResponse with per-claim evidence results.
        """
        company = self.sec_service.get_company_by_ticker(ticker)
        latest_resp = self.sec_service.get_latest_annual_filing(ticker)
        filing = latest_resp.filing

        # Check cache
        cache_key = filing.accession_number
        if cache_key in self._evidence_cache:
            logger.debug("Returning cached evidence for accession %s", cache_key)
            all_results = self._evidence_cache[cache_key]
        else:
            document = self.doc_service.process_document(filing)
            claims_resp = self.claims_service.get_company_claims(ticker, limit=1000)
            all_claims = claims_resp.claims

            all_results: List[ClaimEvidenceResult] = []
            for claim in all_claims:
                evidence_list = self._search_evidence_for_claim(
                    claim=claim,
                    document=document,
                    filing=filing,
                )
                strongest_rel = self._determine_strongest_relationship(evidence_list)
                retrieval_conf = self._overall_retrieval_confidence(evidence_list)
                best_ev = sorted(evidence_list, key=lambda e: e.relevance_score, reverse=True)[
                    :MAX_BEST_EVIDENCE
                ]

                all_results.append(
                    ClaimEvidenceResult(
                        claim=claim,
                        evidence=evidence_list,
                        best_evidence=best_ev,
                        evidence_count=len(evidence_list),
                        strongest_relationship=strongest_rel,
                        overall_retrieval_confidence=retrieval_conf,
                    )
                )

            self._evidence_cache[cache_key] = all_results

        # Apply filters
        filtered_results = all_results

        if category:
            cat_norm = category.strip().lower()
            filtered_results = [
                r for r in filtered_results
                if r.claim.category == cat_norm or r.claim.category_group == cat_norm
            ]

        if claim_type:
            type_norm = claim_type.strip().lower()
            filtered_results = [r for r in filtered_results if r.claim.claim_type == type_norm]

        if relationship:
            rel_norm = relationship.strip().lower()
            filtered_results = [
                r for r in filtered_results
                if r.strongest_relationship == rel_norm
            ]

        if minimum_relevance > 0.0:
            filtered_results = [
                r for r in filtered_results
                if r.best_evidence and r.best_evidence[0].relevance_score >= minimum_relevance
            ]

        bounded_results = filtered_results[:limit]
        total_evidence = sum(r.evidence_count for r in bounded_results)

        return CompanyEvidenceResponse(
            company=company,
            filing_accession_number=filing.accession_number,
            filing_date=filing.filing_date,
            report_date=filing.report_date,
            source_url=filing.filing_url,
            total_claims=len(bounded_results),
            total_evidence_records=total_evidence,
            extraction_method="deterministic",
            results=bounded_results,
        )

    def get_claim_evidence(self, ticker: str, claim_id: str) -> ClaimEvidenceResult:
        """Retrieve evidence for a specific claim by its ID.

        Args:
            ticker: Company stock ticker symbol.
            claim_id: Deterministic claim ID.

        Returns:
            ClaimEvidenceResult for the specified claim.

        Raises:
            ClaimNotFoundError: If the claim ID cannot be found.
        """
        evidence_resp = self.get_company_evidence(ticker, limit=1000)
        for result in evidence_resp.results:
            if result.claim.claim_id == claim_id:
                return result

        # Import here to avoid circular — exceptions module has no service deps
        from app.utils.exceptions import ClaimNotFoundError
        raise ClaimNotFoundError(
            f"Claim with ID '{claim_id}' not found for ticker '{ticker}'."
        )

    def get_evidence_summary(self, ticker: str) -> EvidenceSummaryResponse:
        """Retrieve high-level summary statistics of evidence retrieval.

        Args:
            ticker: Company stock ticker symbol.

        Returns:
            EvidenceSummaryResponse with aggregated counts.

        IMPORTANT: Counts reflect retrieval results only. They do NOT constitute
        an ESG score, greenwashing determination, or legal conclusion.
        """
        latest_resp = self.sec_service.get_latest_annual_filing(ticker)
        company = self.sec_service.get_company_by_ticker(ticker)
        evidence_resp = self.get_company_evidence(ticker, limit=1000)
        results = evidence_resp.results

        claims_with_ev = sum(1 for r in results if r.evidence_count > 0)
        claims_insufficient = sum(
            1 for r in results
            if r.strongest_relationship == EvidenceRelationship.INSUFFICIENT_EVIDENCE.value
            or r.evidence_count == 0
        )

        supporting = 0
        contradictory = 0
        qualifying = 0
        contextual = 0
        strong = 0
        moderate = 0
        weak = 0

        for result in results:
            for ev in result.evidence:
                rel = ev.relationship
                if rel == EvidenceRelationship.SUPPORTING.value:
                    supporting += 1
                elif rel == EvidenceRelationship.CONTRADICTORY.value:
                    contradictory += 1
                elif rel == EvidenceRelationship.QUALIFYING.value:
                    qualifying += 1
                elif rel == EvidenceRelationship.CONTEXTUAL.value:
                    contextual += 1

                str_ = ev.evidence_strength
                if str_ == EvidenceStrength.STRONG.value:
                    strong += 1
                elif str_ == EvidenceStrength.MODERATE.value:
                    moderate += 1
                else:
                    weak += 1

        return EvidenceSummaryResponse(
            company=company,
            filing_accession_number=latest_resp.filing.accession_number,
            total_claims_analyzed=len(results),
            claims_with_evidence=claims_with_ev,
            claims_insufficient_evidence=claims_insufficient,
            supporting_evidence_count=supporting,
            contradictory_evidence_count=contradictory,
            qualifying_evidence_count=qualifying,
            contextual_evidence_count=contextual,
            strong_evidence_count=strong,
            moderate_evidence_count=moderate,
            weak_evidence_count=weak,
            extraction_method="deterministic",
        )


# ─────────────────────────────────────────────────────────
# Singleton Dependency Provider
# ─────────────────────────────────────────────────────────

_evidence_service_instance: Optional[EvidenceService] = None


def get_evidence_service() -> EvidenceService:
    """Dependency provider returning singleton EvidenceService instance."""
    global _evidence_service_instance
    if _evidence_service_instance is None:
        _evidence_service_instance = EvidenceService()
    return _evidence_service_instance
