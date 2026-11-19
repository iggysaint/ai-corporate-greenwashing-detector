"""Live Ghana Stock Exchange verification script.

Verifies the complete GSE pipeline:
1. Company discovery from the Kwayisi GSE API
2. Company ticker lookup
3. Document discovery (stubs)
4. Ghana-specific ESG keyword retrieval
5. (Optional) Document retrieval from a provided URL

Usage:
    python scripts/verify_live_gse.py                  # List all GSE companies
    python scripts/verify_live_gse.py MTNGH            # Look up specific ticker
    python scripts/verify_live_gse.py MTNGH --url URL  # Retrieve document from URL

Note: This script makes live HTTP requests to the Kwayisi GSE API.
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.gse_service import GSEService, GSEServiceError
from app.models.market import DocumentSourceType


def main():
    parser = argparse.ArgumentParser(description="Verify live GSE pipeline")
    parser.add_argument("ticker", nargs="?", default=None, help="GSE ticker symbol (e.g., MTNGH)")
    parser.add_argument("--url", default=None, help="Document URL to retrieve and process")
    parser.add_argument("--source-type", default="annual_report", help="Document source type")
    parser.add_argument("--period", default=None, help="Reporting period (e.g., 2024)")
    args = parser.parse_args()

    print("=" * 65)
    print("LIVE GSE VERIFICATION")
    print("=" * 65)

    service = GSEService()

    try:
        # Step 1: List all companies
        print("\n1. Discovering GSE-listed companies...")
        listing = service.get_listed_companies()
        print(f"   Total companies found: {listing.total_count}")

        if listing.companies:
            print(f"\n   Sample companies (first 10):")
            for i, c in enumerate(listing.companies[:10], 1):
                sector_str = f" | Sector: {c.sector}" if c.sector else ""
                print(f"   [{i:2d}] {c.ticker:10s} {c.company_name}{sector_str}")

        if not args.ticker:
            print("\n" + "=" * 65)
            print("GSE COMPANY LISTING VERIFIED SUCCESSFULLY!")
            print("=" * 65)
            return

        # Step 2: Look up specific ticker
        ticker = args.ticker.upper()
        print(f"\n2. Looking up company: {ticker}...")
        company = service.get_company_by_ticker(ticker)
        print(f"   Ticker:       {company.ticker}")
        print(f"   Name:         {company.company_name}")
        print(f"   Market:       {company.market.value}")
        print(f"   Sector:       {company.sector or 'N/A'}")
        print(f"   Currency:     {company.currency}")
        if company.market_cap:
            print(f"   Market Cap:   {company.market_cap:,.0f} {company.currency}")

        # Step 3: Discover documents
        print(f"\n3. Discovering available documents for {ticker}...")
        detail = service.discover_company_documents(ticker)
        print(f"   Document stubs created: {len(detail.documents)}")
        for doc in detail.documents:
            print(f"   - {doc.source_type.value}: {doc.title} [{doc.retrieval_status}]")

        # Step 4: Ghana-specific ESG keywords
        print(f"\n4. Ghana-specific ESG keywords for sector '{company.sector or 'general'}':")
        keywords = GSEService.get_ghana_esg_keywords(sector=company.sector)
        for i in range(0, len(keywords), 4):
            chunk = keywords[i:i + 4]
            print(f"   {', '.join(chunk)}")

        # Step 5: Document retrieval (if URL provided)
        if args.url:
            print(f"\n5. Retrieving document from URL...")
            print(f"   URL: {args.url}")

            source_type_map = {
                "annual_report": DocumentSourceType.ANNUAL_REPORT,
                "sustainability_report": DocumentSourceType.SUSTAINABILITY_REPORT,
                "integrated_report": DocumentSourceType.INTEGRATED_REPORT,
            }
            source_type = source_type_map.get(args.source_type, DocumentSourceType.ANNUAL_REPORT)

            doc = service.retrieve_document_from_url(
                ticker=ticker,
                source_url=args.url,
                source_type=source_type,
                reporting_period=args.period,
            )

            print(f"   Document ID:     {doc.document_id}")
            print(f"   Status:          {doc.retrieval_status}")
            print(f"   Format:          {doc.format}")

            if doc.retrieval_status == "retrieved":
                print(f"   Text Length:     {doc.text_length:,} characters")
                print(f"   Word Count:      {doc.word_count:,} words")
                if doc.page_count:
                    print(f"   Page Count:      {doc.page_count}")
                print(f"\n   First 500 characters of extracted text:")
                print(f"   {'-' * 55}")
                preview = doc.text_content[:500] if doc.text_content else "(empty)"
                for line in preview.split("\n")[:10]:
                    print(f"   {line}")
            else:
                print(f"   Error:           {doc.error_message}")

        print("\n" + "=" * 65)
        print("GSE PIPELINE VERIFIED SUCCESSFULLY!")
        print("=" * 65)

    except GSEServiceError as err:
        print(f"\n   ERROR: {err}")
        print("\n" + "=" * 65)
        print("GSE VERIFICATION FAILED")
        print("=" * 65)
        sys.exit(1)
    except Exception as err:
        print(f"\n   UNEXPECTED ERROR: {type(err).__name__}: {err}")
        sys.exit(1)
    finally:
        service.close()


if __name__ == "__main__":
    main()
