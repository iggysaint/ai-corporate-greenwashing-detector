"""Sustainability Claim Extraction and Structuring Service."""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.models.claim import (
    CATEGORY_TO_GROUP,
    Claim,
    ClaimCategoryGroup,
    ClaimSummaryResponse,
    ClaimType,
    CompanyClaimsResponse,
    SourceReference,
)
from app.models.company import Company
from app.models.document import Document, DocumentSection
from app.models.filing import SECFiling
from app.services.document_service import DocumentService, get_document_service
from app.services.sec_service import SECService, get_sec_service
from app.utils.config import Settings, get_settings
from app.utils.exceptions import ClaimNotFoundError

logger = logging.getLogger(__name__)

# Sentence splitting regex that protects decimal numbers (e.g. $12.4 billion, 25.5%)
SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?])(?<!\d\.)\s+(?=[A-Z0-9\"'])")

# Patterns indicating purely hypothetical risk/forward-looking disclosures to filter out
RISK_DISCLAIMER_PATTERNS = [
    re.compile(r"\b(?:could|can|may)\s+(?:materially\s+)?adversely\s+affect\b", re.I),
    re.compile(r"\bthere\s+can\s+be\s+no\s+assurance\b", re.I),
    re.compile(r"\buncertainties\s+that\s+could\s+cause\b", re.I),
    re.compile(r"\bmay\s+(?:be\s+)?subject\s+to\s+(?:increased\s+)?costs\b", re.I),
    re.compile(r"\bstatements\s+that\s+are\s+not\s+historical\s+facts\b", re.I),
    re.compile(r"\bforward-looking\s+statements\b", re.I),
    re.compile(r"\brisk\s+factor(?:s)?\s+that\s+could\b", re.I),
]

# Patterns indicating affirmative commitments / targets
TARGET_PATTERNS = [
    re.compile(r"\b(?:aim|aims|aiming)\s+to\b", re.I),
    re.compile(r"\b(?:commit|commits|committed)\s+to\b", re.I),
    re.compile(r"\b(?:commitment|commitments)\s+to\b", re.I),
    re.compile(r"\b(?:target|targets|targeting)\s+(?:of|to|for)\b", re.I),
    re.compile(r"\b(?:goal|goals)\s+(?:of|is|to)\b", re.I),
    re.compile(r"\b(?:plan|plans|planning)\s+to\b", re.I),
    re.compile(r"\b(?:pledge|pledges|pledged)\s+to\b", re.I),
    re.compile(r"\b(?:working|striving)\s+toward\b", re.I),
    re.compile(r"\b(?:aspire|aspires|aspiring)\s+to\b", re.I),
    re.compile(r"\b(?:intend|intends|intending)\s+to\b", re.I),
    re.compile(r"\b(?:net[- ]zero|carbon[- ]neutral)\s+by\s+(?:20[2-5][0-9])\b", re.I),
]

# Patterns indicating verified achievements / past milestones
ACHIEVEMENT_PATTERNS = [
    re.compile(r"\b(?:achieved|achieving)\b", re.I),
    re.compile(r"\b(?:reduced|decreasing|decreased)\s+(?:our\s+|its\s+|total\s+)?(?:[a-z0-9\-]+\s+){0,3}(?:greenhouse\s+gas|carbon|emissions|water|waste|electricity|energy|diesel)\b", re.I),
    re.compile(r"\b(?:diverted|diverting)\s+\d+%\b", re.I),
    re.compile(r"\b(?:reached|attained|exceeded|surpassed)\b", re.I),
    re.compile(r"\b(?:delivered|eliminated)\s+(?:our\s+|its\s+|total\s+)?(?:greenhouse\s+gas\s+|carbon\s+|emissions|water|waste|single-use|hazardous)\b", re.I),
    re.compile(r"\b(?:transitioned|completed)\s+(?:to\s+)?\d+%\b", re.I),
]

# Patterns indicating operational current state performance
CURRENT_STATE_PATTERNS = [
    re.compile(r"\b(?:powers|utilizes|sources)\s+100%\s+renewable\b", re.I),
    re.compile(r"\b(?:currently\s+powers|currently\s+utilizes|currently\s+sources)\b", re.I),
    re.compile(r"\b(?:operations\s+are\s+powered\s+by)\b", re.I),
    re.compile(r"\b(?:workforce\s+(?:consists\s+of|included|totaled|comprises))\b", re.I),
    re.compile(r"\b(?:represented\s+\d+%\s+of\s+(?:our|total))\b", re.I),
]

# Patterns indicating stated policies, codes of conduct, or governance frameworks
POLICY_PATTERNS = [
    re.compile(
        r"\b(?:maintain|maintains|adhere|adheres|implemented|established|in\s+place)\s+(?:a\s+|an\s+)?(?:[a-z0-9\-]+\s+){0,3}(?:policy|code\s+of\s+conduct|standard(?:s)?|framework|program|system)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:supplier\s+code\s+of\s+conduct|human\s+rights\s+policy|environmental\s+policy|environmental\s+management\s+system|code\s+of\s+(?:business\s+)?ethics|code\s+of\s+conduct|compliance\s+program)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:equal\s+opportunity\s+employer|non[- ]discrimination|workplace\s+free\s+of\s+harassment)\b",
        re.I,
    ),
]

# Category matching rules (ordered by specificity)
CATEGORY_MATCHERS = [
    ("renewable_energy", re.compile(r"\b(?:renewable\s+energy|clean\s+electricity|solar|wind|green\s+power)\b", re.I)),
    ("greenhouse_gas", re.compile(r"\b(?:greenhouse\s+gas|ghg|scope\s+1|scope\s+2|scope\s+3)\b", re.I)),
    ("carbon", re.compile(r"\b(?:carbon\s+neutral|carbon\s+emissions|carbon\s+footprint|decarbonization|net[- ]zero)\b", re.I)),
    ("emissions", re.compile(r"\b(?:emissions|air\s+emissions)\b", re.I)),
    ("water", re.compile(r"\b(?:water\s+consumption|water\s+usage|water\s+withdrawal|water\s+efficiency|water\s+discharge|water\s+stewardship|water\s+recycling)\b", re.I)),
    ("waste", re.compile(r"\b(?:waste\s+diversion|zero\s+waste|landfill|hazardous\s+waste|waste\s+reduction|e-waste|electronic\s+waste)\b", re.I)),
    ("recycling", re.compile(r"\b(?:recycling|recycled\s+content|recycled\s+materials|recyclable)\b", re.I)),
    ("circular_economy", re.compile(r"\b(?:circular\s+economy|closed[- ]loop|refurbishment)\b", re.I)),
    ("energy", re.compile(r"\b(?:energy\s+efficiency|energy\s+consumption|energy\s+conservation)\b", re.I)),
    ("biodiversity", re.compile(r"\b(?:biodiversity|ecosystems|habitat\s+conservation)\b", re.I)),
    ("environmental_management", re.compile(r"\b(?:environmental\s+policy|environmental\s+management|iso\s+14001|environmental\s+standards)\b", re.I)),
    ("climate", re.compile(r"\b(?:climate\s+change|climate\s+strategy|climate\s+transition|climate\s+goals?)\b", re.I)),
    ("diversity", re.compile(r"\b(?:diversity|underrepresented\s+communities|gender\s+diversity|ethnic\s+diversity|dei)\b", re.I)),
    ("inclusion", re.compile(r"\b(?:inclusion|inclusive\s+workplace|digital\s+inclusion|financial\s+inclusion)\b", re.I)),
    ("health_and_safety", re.compile(r"\b(?:health\s+and\s+safety|occupational\s+safety|workplace\s+safety|safety\s+and\s+security\s+of\s+(?:its\s+|our\s+)?(?:team\s+members|employees|workers)|injury\s+rate)\b", re.I)),
    ("human_rights", re.compile(r"\b(?:human\s+rights|forced\s+labor|child\s+labor|trafficking)\b", re.I)),
    ("labor", re.compile(r"\b(?:labor\s+standards|fair\s+labor|collective\s+bargaining|fair\s+wages)\b", re.I)),
    ("supply_chain", re.compile(r"\b(?:supplier\s+responsibility|supplier\s+code|supply\s+chain\s+audits|vendor\s+standards)\b", re.I)),
    ("workforce", re.compile(r"\b(?:workforce|talent\s+development|personnel)\b", re.I)),
    ("employees", re.compile(r"\b(?:employees|full-time\s+equivalent\s+employees|staff)\b", re.I)),
    ("community", re.compile(r"\b(?:community|communities|philanthropy|local\s+giving|community\s+development|social\s+investment)\b", re.I)),
    ("board", re.compile(r"\b(?:board\s+of\s+directors|board\s+committee|board\s+oversight|independent\s+directors)\b", re.I)),
    ("ethics", re.compile(r"\b(?:code\s+of\s+ethics|business\s+ethics|anti-corruption|anti-bribery)\b", re.I)),
    ("business_conduct", re.compile(r"\b(?:business\s+conduct|business\s+standards)\b", re.I)),
    ("compliance", re.compile(r"\b(?:compliance\s+program|regulatory\s+compliance|legal\s+compliance)\b", re.I)),
    ("risk_management", re.compile(r"\b(?:risk\s+management|risk\s+oversight|enterprise\s+risk)\b", re.I)),
    ("transparency", re.compile(r"\b(?:transparency|esg\s+reporting|sustainability\s+disclosure)\b", re.I)),
    ("governance", re.compile(r"\b(?:corporate\s+governance|governance\s+guidelines)\b", re.I)),
    ("sustainability", re.compile(r"\b(?:sustainability|sustainable\s+operations|sustainable\s+practices|sustainable\s+future)\b", re.I)),
]


class ClaimsService:
    """Service for extracting, normalizing, and structuring sustainability claims from SEC filings."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        sec_service: Optional[SECService] = None,
        doc_service: Optional[DocumentService] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sec_service = sec_service or get_sec_service()
        self.doc_service = doc_service or get_document_service()
        # In-memory claim store keyed by filing accession number
        self._claims_cache: Dict[str, List[Claim]] = {}

    def clear_cache(self) -> None:
        """Clear the in-memory claims cache."""
        self._claims_cache.clear()

    @staticmethod
    def generate_claim_id(
        company_ticker: str,
        accession_number: str,
        section_id: str,
        claim_text: str,
    ) -> str:
        """Generate a stable, deterministic claim ID based on content hashing."""
        norm_text = re.sub(r"[^a-z0-9]", "", claim_text.lower())
        hash_seed = f"{company_ticker.upper()}_{accession_number}_{section_id}_{norm_text}"
        digest = hashlib.sha256(hash_seed.encode("utf-8")).hexdigest()[:12]
        clean_accession = accession_number.replace("-", "_")
        return f"claim_{company_ticker.lower()}_{clean_accession}_{digest}"

    def is_risk_disclaimer(self, text: str) -> bool:
        """Determine if a sentence is purely a risk/uncertainty disclosure rather than an affirmative claim."""
        for pattern in RISK_DISCLAIMER_PATTERNS:
            if pattern.search(text):
                # If it's a disclaimer, check whether it ALSO has an explicit commitment or achievement
                has_affirmative_target = any(tp.search(text) for tp in TARGET_PATTERNS)
                has_affirmative_achievement = any(ap.search(text) for ap in ACHIEVEMENT_PATTERNS)
                has_affirmative_policy = any(pp.search(text) for pp in POLICY_PATTERNS)
                if not (has_affirmative_target or has_affirmative_achievement or has_affirmative_policy):
                    return True
        return False

    def classify_claim_type(self, sentence: str) -> Optional[ClaimType]:
        """Classify a sentence into a claim type, or return None if not a claim."""
        # 1. Policy / Practice (checked first to prioritize formal governance/code of conduct commitments)
        if any(p.search(sentence) for p in POLICY_PATTERNS):
            return ClaimType.POLICY

        # 2. Target / Commitment
        if any(p.search(sentence) for p in TARGET_PATTERNS):
            return ClaimType.TARGET

        # 3. Achievement
        if any(p.search(sentence) for p in ACHIEVEMENT_PATTERNS):
            return ClaimType.ACHIEVEMENT

        # 4. Current State / Performance
        if any(p.search(sentence) for p in CURRENT_STATE_PATTERNS):
            return ClaimType.CURRENT_STATE

        # 5. General Sustainability Statement
        # Matches broad affirmative statements mentioning sustainability commitment
        general_match = re.search(
            r"\b(?:committed to|investing in|supports|promotes|focuses on)\s+(?:environmental|sustainability|renewable|diversity|inclusion|community)\b",
            sentence,
            re.I,
        )
        if general_match:
            return ClaimType.GENERAL

        return None

    def match_category(self, text: str) -> Tuple[Optional[str], Optional[ClaimCategoryGroup]]:
        """Identify the most specific applicable ESG category and its parent pillar.

        Returns (None, None) if the text does not contain recognized ESG or sustainability subject matter.
        """
        for cat_name, pattern in CATEGORY_MATCHERS:
            if pattern.search(text):
                group = CATEGORY_TO_GROUP.get(cat_name, ClaimCategoryGroup.OTHER)
                return cat_name, group

        return None, None

    def extract_quantitative_target(
        self,
        sentence: str,
    ) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[int], Optional[str]]:
        """Extract quantitative values, unit, target year, baseline year, and metric.

        Returns:
            Tuple of (target_value, unit, target_year, baseline_year, metric).
        """
        target_value: Optional[str] = None
        unit: Optional[str] = None
        target_year: Optional[int] = None
        baseline_year: Optional[int] = None
        metric: Optional[str] = None

        # 1. Target Year (e.g. by 2030, in 2050)
        target_yr_match = re.search(r"\b(?:by|in|through|target year)\s+(20[2-5][0-9])\b", sentence, re.I)
        if target_yr_match:
            target_year = int(target_yr_match.group(1))

        # 2. Baseline Year (e.g. from 2020 baseline, compared with 2019)
        base_yr_match = re.search(
            r"\b(?:compared with|from|against|over)(?:\s+our)?\s+(?:a\s+)?(20[0-2][0-9])(?:\s+baseline|\s+levels)?\b",
            sentence,
            re.I,
        )
        if base_yr_match:
            baseline_year = int(base_yr_match.group(1))

        # 3. Quantitative Target Value & Unit
        # Percentage match (no \b after % since % is non-word char)
        pct_match = re.search(r"\b(\d+(?:\.\d+)?%)(?!\w)", sentence)
        if pct_match:
            target_value = pct_match.group(1)
            unit = "percent"
        else:
            # Volume / Energy / Metric tons
            qty_match = re.search(
                r"\b(\d+(?:,\d+)*(?:\.\d+)?\s*(?:metric\s+tons?|tonnes?|mwh|gwh|mw|gallons?|liters?))\b",
                sentence,
                re.I,
            )
            if qty_match:
                target_value = qty_match.group(1)
                unit_raw = qty_match.group(1).split()[-1].lower()
                unit = "metric_tons" if "ton" in unit_raw else unit_raw
            elif re.search(r"\b(?:net[- ]zero)\b", sentence, re.I):
                target_value = "net zero"
                unit = "net_zero"
            elif re.search(r"\b(?:carbon[- ]neutral)\b", sentence, re.I):
                target_value = "carbon neutral"
                unit = "carbon_neutral"

        # 4. Metric subject identification
        if re.search(r"\b(?:scope\s+1\s+and\s+scope\s+2|scope\s+1|scope\s+2|scope\s+3)\b", sentence, re.I):
            scope_m = re.search(r"\b(scope\s+1(?:\s+and\s+scope\s+2)?(?:\s+greenhouse\s+gas)?(?:\s+emissions)?)\b", sentence, re.I)
            metric = scope_m.group(1) if scope_m else "greenhouse gas emissions"
        elif re.search(r"\b(?:greenhouse\s+gas\s+emissions|ghg\s+emissions)\b", sentence, re.I):
            metric = "greenhouse gas emissions"
        elif re.search(r"\b(?:carbon\s+emissions)\b", sentence, re.I):
            metric = "carbon emissions"
        elif re.search(r"\b(?:renewable\s+energy)\b", sentence, re.I):
            metric = "renewable energy"
        elif re.search(r"\b(?:water\s+consumption|water\s+usage)\b", sentence, re.I):
            metric = "water consumption"
        elif re.search(r"\b(?:waste\s+diversion|waste)\b", sentence, re.I):
            metric = "waste"

        return target_value, unit, target_year, baseline_year, metric

    def extract_claims_from_document(
        self,
        company: Company,
        filing: SECFiling,
        document: Document,
    ) -> List[Claim]:
        """Extract, categorize, normalize, and deduplicate sustainability claims from a Document.

        Args:
            company: Company identification model.
            filing: Source SEC filing model.
            document: Processed Document model.

        Returns:
            List of structured, deduplicated Claim models.
        """
        accession = filing.accession_number
        if accession in self._claims_cache:
            logger.debug("Returning cached claims for accession %s", accession)
            return self._claims_cache[accession]

        extracted_claims: List[Claim] = []
        # Normalization map for duplicate detection: norm_text -> index in extracted_claims
        seen_claim_texts: Dict[str, int] = {}

        # Prioritize relevant sections
        sections_to_process = document.sections
        if not sections_to_process:
            sections_to_process = [
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

        for section in sections_to_process:
            # Process paragraphs
            paragraphs = section.text.split("\n\n")

            for para in paragraphs:
                para_clean = para.strip()
                if not para_clean or len(para_clean) < 20:
                    continue

                # Split paragraph into sentences
                sentences = [s.strip() for s in SENTENCE_SPLIT_REGEX.split(para_clean) if s.strip()]

                for sentence in sentences:
                    if len(sentence) < 25:
                        continue

                    # Filter out purely hypothetical risk disclaimers
                    if self.is_risk_disclaimer(sentence):
                        continue

                    # Check for claim type
                    claim_type = self.classify_claim_type(sentence)
                    if not claim_type:
                        continue

                    # Identify category and parent pillar
                    category, cat_group = self.match_category(sentence)
                    if not category or not cat_group:
                        continue

                    # Extract quantitative parameters
                    target_val, unit, target_yr, base_yr, metric = self.extract_quantitative_target(sentence)

                    # Confidence assignment
                    if target_val is not None and (target_yr is not None or base_yr is not None):
                        confidence = "high"
                    elif target_val is not None or claim_type in (ClaimType.TARGET, ClaimType.ACHIEVEMENT):
                        confidence = "high"
                    elif claim_type == ClaimType.POLICY:
                        confidence = "medium"
                    else:
                        confidence = "medium" if claim_type == ClaimType.CURRENT_STATE else "low"

                    status = "validated" if confidence in ("high", "medium") else "candidate"

                    # Normalize text for deduplication
                    norm_text = re.sub(r"[^a-z0-9]", "", sentence.lower())

                    if norm_text in seen_claim_texts:
                        # Existing claim found: record additional source reference
                        existing_idx = seen_claim_texts[norm_text]
                        existing_claim = extracted_claims[existing_idx]

                        # Only add if from a different section
                        if existing_claim.section_id != section.section_id:
                            ref = SourceReference(
                                source_type="sec_10k",
                                source_title=document.title or f"{filing.form_type} Annual Report",
                                source_url=filing.filing_url,
                                filing_accession_number=accession,
                                section_id=section.section_id,
                                section_title=section.section_title,
                                source_excerpt=para_clean[:400],
                                source_location=section.section_title,
                            )
                            existing_claim.additional_sources.append(ref)
                        continue

                    # Generate stable deterministic ID
                    claim_id = self.generate_claim_id(
                        company_ticker=company.ticker,
                        accession_number=accession,
                        section_id=section.section_id,
                        claim_text=sentence,
                    )

                    claim = Claim(
                        claim_id=claim_id,
                        company_ticker=company.ticker,
                        company_name=company.company_name,
                        claim_text=sentence,
                        claim_type=claim_type.value,
                        category=category,
                        category_group=cat_group.value,
                        source_type="sec_10k",
                        source_title=document.title or f"{filing.form_type} Annual Report",
                        source_url=filing.filing_url,
                        filing_accession_number=accession,
                        filing_date=filing.filing_date,
                        report_date=filing.report_date,
                        section_id=section.section_id,
                        section_title=section.section_title,
                        source_excerpt=para_clean[:600],
                        source_location=section.section_title,
                        target_year=target_yr,
                        baseline_year=base_yr,
                        metric=metric,
                        target_value=target_val,
                        unit=unit,
                        claim_date=None,
                        extraction_method="deterministic",
                        confidence=confidence,
                        status=status,
                        additional_sources=[],
                    )

                    seen_claim_texts[norm_text] = len(extracted_claims)
                    extracted_claims.append(claim)

        logger.info(
            "Extracted %d structured sustainability claims from filing %s for %s",
            len(extracted_claims),
            accession,
            company.ticker,
        )

        self._claims_cache[accession] = extracted_claims
        return extracted_claims

    def get_company_claims(
        self,
        ticker: str,
        category: Optional[str] = None,
        claim_type: Optional[str] = None,
        limit: int = 50,
    ) -> CompanyClaimsResponse:
        """Retrieve and filter structured sustainability claims for the company's latest 10-K.

        Args:
            ticker: Company stock ticker symbol.
            category: Optional category filter (e.g. 'greenhouse_gas', 'renewable_energy').
            claim_type: Optional claim type filter (e.g. 'target', 'achievement', 'policy').
            limit: Maximum claims to return (default 50).

        Returns:
            CompanyClaimsResponse containing company, filing, and filtered claims.
        """
        company = self.sec_service.get_company_by_ticker(ticker)
        latest_filing_resp = self.sec_service.get_latest_annual_filing(ticker)
        filing = latest_filing_resp.filing

        document = self.doc_service.process_document(filing)
        all_claims = self.extract_claims_from_document(company, filing, document)

        # Apply filters
        filtered_claims = all_claims
        if category:
            cat_norm = category.strip().lower()
            filtered_claims = [
                c for c in filtered_claims
                if c.category == cat_norm or c.category_group == cat_norm
            ]

        if claim_type:
            type_norm = claim_type.strip().lower()
            filtered_claims = [c for c in filtered_claims if c.claim_type == type_norm]

        bounded_claims = filtered_claims[:limit]

        return CompanyClaimsResponse(
            company=company,
            filing=filing,
            total_claims=len(bounded_claims),
            claims=bounded_claims,
            extraction_metadata={
                "extraction_method": "deterministic",
                "filing_accession": filing.accession_number,
                "total_extracted_unfiltered": len(all_claims),
                "filter_category": category,
                "filter_claim_type": claim_type,
            },
        )

    def get_claim_by_id(self, ticker: str, claim_id: str) -> Claim:
        """Retrieve an individual claim record by its deterministic ID.

        Args:
            ticker: Company stock ticker symbol.
            claim_id: Deterministic claim ID.

        Returns:
            Structured Claim model.

        Raises:
            ClaimNotFoundError: If claim ID does not exist for the company's latest filing.
        """
        claims_resp = self.get_company_claims(ticker, limit=1000)
        for claim in claims_resp.claims:
            if claim.claim_id == claim_id:
                return claim

        raise ClaimNotFoundError(f"Claim with ID '{claim_id}' not found for ticker '{ticker}'.")

    def get_claim_summary(self, ticker: str) -> ClaimSummaryResponse:
        """Generate high-level counts and breakdown of sustainability claims by pillar and type.

        Args:
            ticker: Company stock ticker symbol.

        Returns:
            ClaimSummaryResponse containing categorical metrics.
        """
        claims_resp = self.get_company_claims(ticker, limit=1000)
        claims = claims_resp.claims

        env_count = sum(1 for c in claims if c.category_group == ClaimCategoryGroup.ENVIRONMENTAL.value)
        soc_count = sum(1 for c in claims if c.category_group == ClaimCategoryGroup.SOCIAL.value)
        gov_count = sum(1 for c in claims if c.category_group == ClaimCategoryGroup.GOVERNANCE.value)

        target_count = sum(1 for c in claims if c.claim_type == ClaimType.TARGET.value)
        achieve_count = sum(1 for c in claims if c.claim_type == ClaimType.ACHIEVEMENT.value)
        policy_count = sum(1 for c in claims if c.claim_type == ClaimType.POLICY.value)
        current_count = sum(1 for c in claims if c.claim_type == ClaimType.CURRENT_STATE.value)
        general_count = sum(1 for c in claims if c.claim_type == ClaimType.GENERAL.value)

        by_cat: Dict[str, int] = {}
        for c in claims:
            by_cat[c.category] = by_cat.get(c.category, 0) + 1

        by_type: Dict[str, int] = {}
        for c in claims:
            by_type[c.claim_type] = by_type.get(c.claim_type, 0) + 1

        return ClaimSummaryResponse(
            company=claims_resp.company,
            filing_accession_number=claims_resp.filing.accession_number,
            total_claims=len(claims),
            environmental_claims=env_count,
            social_claims=soc_count,
            governance_claims=gov_count,
            target_claims=target_count,
            achievement_claims=achieve_count,
            policy_claims=policy_count,
            current_state_claims=current_count,
            general_claims=general_count,
            by_category=by_cat,
            by_claim_type=by_type,
        )


_claims_service_instance: Optional[ClaimsService] = None


def get_claims_service() -> ClaimsService:
    """Dependency provider returning singleton ClaimsService instance."""
    global _claims_service_instance
    if _claims_service_instance is None:
        _claims_service_instance = ClaimsService()
    return _claims_service_instance
