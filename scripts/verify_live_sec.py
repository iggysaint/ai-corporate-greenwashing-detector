"""Manual verification script to test live SEC EDGAR integration with Apple Inc. (AAPL).

Usage:
    python scripts/verify_live_sec.py
    python scripts/verify_live_sec.py MSFT
"""

import os
import sys

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.claims_service import ClaimsService
from app.services.document_service import DocumentService
from app.services.evidence_service import EvidenceService
from app.services.llm_service import LLMService
from app.services.sec_service import SECService
from app.utils.config import get_settings


def verify_ticker(ticker: str = "AAPL") -> None:
    settings = get_settings()
    print("=" * 65)
    print(f"LIVE SEC VERIFICATION FOR TICKER: {ticker}")
    print(f"Configured User-Agent: {settings.SEC_USER_AGENT}")
    print("=" * 65)

    with SECService(settings=settings) as sec_service, DocumentService(settings=settings) as doc_service:
        claims_service = ClaimsService(settings=settings, sec_service=sec_service, doc_service=doc_service)

        print("\n1. Resolving company metadata...")
        company = sec_service.get_company_by_ticker(ticker)
        print(f"   Ticker:       {company.ticker}")
        print(f"   Name:         {company.company_name}")
        print(f"   CIK:          {company.cik}")
        print(f"   Exchange:     {company.exchange}")
        print(f"   SIC:          {company.sic} ({company.sic_description})")

        print("\n2. Discovering annual filings (10-K, 10-K/A)...")
        filings_resp = sec_service.get_company_filings(ticker)
        print(f"   Total annual filings discovered: {filings_resp.total_count}")

        print("\n3. Selecting latest prevailing annual filing...")
        latest_resp = sec_service.get_latest_annual_filing(ticker)
        latest = latest_resp.filing
        print(f"   Form Type:        {latest.form_type}")
        print(f"   Filing Date:      {latest.filing_date}")
        print(f"   Report Date:      {latest.report_date}")
        print(f"   Fiscal Year:      {latest.fiscal_year}")
        print(f"   Accession Number: {latest.accession_number}")
        print(f"   Primary Document: {latest.primary_document}")
        print(f"   Filing URL:       {latest.filing_url}")

        print("\n4. Ingesting, parsing, and cleaning 10-K document...")
        doc = doc_service.process_document(latest)
        print(f"   Cleaned Text Length: {len(doc.text):,} characters")
        print(f"   Total Word Count:    {doc.word_count:,} words")
        print(f"   Document Title:      {doc.title}")

        print(f"\n5. Detecting 10-K document sections ({len(doc.sections)} detected)...")
        for i, sec in enumerate(doc.sections[:6], 1):
            print(f"   [{i}] {sec.section_title} | Type: {sec.section_type} | Words: {sec.word_count:,}")

        print("\n6. Extracting traceable ESG passages...")
        passages = doc_service.find_relevant_passages(
            document=doc,
            company_ticker=company.ticker,
            max_passages=5,
        )
        print(f"   Total matching passages found: {len(passages)}")

        print("\n" + "=" * 65)
        print("PHASE 4: SUSTAINABILITY CLAIM EXTRACTION")
        print("=" * 65)
        print(f"Company: {company.company_name}")
        print(f"Ticker:  {company.ticker}")
        print(f"Filing:  {latest.fiscal_year} Form {latest.form_type}")

        claims = claims_service.extract_claims_from_document(company, latest, doc)
        summary = claims_service.get_claim_summary(company.ticker)

        print(f"\nClaims extracted: {summary.total_claims}")
        print(f"  Environmental: {summary.environmental_claims}")
        print(f"  Social:        {summary.social_claims}")
        print(f"  Governance:    {summary.governance_claims}")
        print(f"\nBreakdown by Claim Type:")
        print(f"  Targets/Commitments:   {summary.target_claims}")
        print(f"  Achievements:          {summary.achievement_claims}")
        print(f"  Current State/Metrics: {summary.current_state_claims}")
        print(f"  Policies/Standards:    {summary.policy_claims}")
        print(f"  General Statements:    {summary.general_claims}")

        print("\nSample Extracted Claims:")
        for i, claim in enumerate(claims[:6], 1):
            target_str = f" | Target Value: {claim.target_value}" if claim.target_value else ""
            target_yr_str = f" | Target Year: {claim.target_year}" if claim.target_year else ""
            print(f"\n[{i}] ID: {claim.claim_id}")
            print(f"    Type:       {claim.claim_type}")
            print(f"    Category:   {claim.category} ({claim.category_group})")
            print(f"    Claim:      \"{claim.claim_text}\"")
            print(f"    Source:     {claim.section_title}{target_str}{target_yr_str}")
            print(f"    Confidence: {claim.confidence} | Status: {claim.status}")

        print("\n" + "=" * 65)
        print("PHASE 5: EVIDENCE & CROSS-REFERENCE ENGINE")
        print("=" * 65)
        evidence_service = EvidenceService(
            settings=settings,
            sec_service=sec_service,
            doc_service=doc_service,
            claims_service=claims_service,
        )

        ev_summary = evidence_service.get_evidence_summary(company.ticker)
        print(f"\nEvidence Retrieval Summary for {company.company_name} ({company.ticker}):")
        print(f"  Total Claims Analyzed:        {ev_summary.total_claims_analyzed}")
        print(f"  Claims With Evidence Found:   {ev_summary.claims_with_evidence}")
        print(f"  Claims Insufficient Evidence: {ev_summary.claims_insufficient_evidence}")
        print(f"\nBreakdown by Relationship (Retrieval Classifications):")
        print(f"  Supporting:    {ev_summary.supporting_evidence_count}")
        print(f"  Contradictory: {ev_summary.contradictory_evidence_count}")
        print(f"  Qualifying:    {ev_summary.qualifying_evidence_count}")
        print(f"  Contextual:    {ev_summary.contextual_evidence_count}")
        print(f"\nBreakdown by Strength:")
        print(f"  Strong:   {ev_summary.strong_evidence_count}")
        print(f"  Moderate: {ev_summary.moderate_evidence_count}")
        print(f"  Weak:     {ev_summary.weak_evidence_count}")

        ev_resp = evidence_service.get_company_evidence(company.ticker, limit=4)
        print(f"\nSample Claim-Evidence Pairs:")
        for i, res in enumerate(ev_resp.results[:4], 1):
            print(f"\n[{i}] Claim: \"{res.claim.claim_text[:90]}...\"")
            print(f"    Claim Type:   {res.claim.claim_type} | Category: {res.claim.category}")
            print(f"    Relationship: {res.strongest_relationship} | Retrieval Confidence: {res.overall_retrieval_confidence}")
            print(f"    Total Evidence Records Found: {res.evidence_count}")
            if res.best_evidence:
                top = res.best_evidence[0]
                print(f"    Top Evidence: [{top.evidence_strength.upper()} | {top.relationship}] {top.section_title}")
                print(f"    Excerpt:      \"{top.evidence_text[:110]}...\"")
                print(f"    Relevance:    {top.relevance_score:.2f} | Matched: {top.matched_terms[:4]}")

        print("\n" + "=" * 65)
        print("PHASE 6: LLM-ASSISTED CONSISTENCY EVALUATION")
        print("=" * 65)
        llm_service = LLMService(
            settings=settings,
            sec_service=sec_service,
            doc_service=doc_service,
            claims_service=claims_service,
            evidence_service=evidence_service,
        )

        print(f"\nActive Provider Mode: {llm_service.active_provider_mode.upper()}")
        if llm_service.is_live_llm_available:
            print(f"Configured Model:     {settings.LLM_MODEL}")
        else:
            print("Note: OPENAI_API_KEY is not set. Evaluations are produced using the deterministic rule-based engine.")

        eval_resp = llm_service.evaluate_company_filing(company.ticker)
        eval_summary = eval_resp.summary

        print(f"\nEvaluation Summary for {company.company_name} ({company.ticker}):")
        print(f"  Total Claims Extracted:      {eval_summary.total_claims_extracted}")
        print(f"  Excluded (Non-ESG):          {eval_summary.excluded_claims_count}")
        print(f"  Total Claims Evaluated:      {eval_summary.total_claims_evaluated}")
        print(f"  Supported:                   {eval_summary.supported_count}")
        print(f"  Partially Supported:         {eval_summary.partially_supported_count}")
        print(f"  Inconsistent:                {eval_summary.inconsistent_count}")
        print(f"  Unsubstantiated:             {eval_summary.unsubstantiated_count}")
        print(f"  Insufficient Evidence:       {eval_summary.insufficient_evidence_count}")
        print(f"  Rule-Based Evaluations:      {eval_summary.rule_based_evaluations_count}")
        print(f"  LLM Evaluations:             {eval_summary.llm_evaluations_count}")

        print(f"\nSample Evaluated Claims:")
        for i, ev_item in enumerate(eval_resp.evaluations[:4], 1):
            print(f"\n[{i}] Claim: \"{ev_item.claim_text[:85]}...\"")
            print(f"    Claim Type:   {ev_item.claim_type} | Category: {ev_item.category}")
            print(f"    Assessment:   {ev_item.assessment.value.upper()} (Confidence: {ev_item.confidence.value})")
            print(f"    Mode:         {ev_item.evaluation_mode.value}")
            print(f"    Reasoning:    {ev_item.reasoning[:120]}...")
            if ev_item.caveats:
                print(f"    Caveats:      {ev_item.caveats[0][:100]}...")
            if ev_item.referenced_evidence:
                ref = ev_item.referenced_evidence[0]
                print(f"    Cited Ref:    [{ref.evidence_id}] {ref.section_id} (Relevance: {ref.relevance_score:.2f})")

    print("\n" + "=" * 65)
    print("PHASES 1–6 LIVE SEC PIPELINE VERIFIED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    target_ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    verify_ticker(target_ticker)
