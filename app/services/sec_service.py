"""SEC EDGAR Data Acquisition and Filing Discovery Service."""

import logging
import re
from typing import Dict, List, Optional, Tuple
import httpx

from app.models.company import Company
from app.models.filing import CompanyFilingsResponse, CompanyLatestFilingResponse, SECFiling
from app.utils.config import Settings, get_settings
from app.utils.exceptions import (
    CompanyNotFoundError,
    FilingNotFoundError,
    SECConnectionError,
    SECRateLimitError,
    SECServiceError,
    TickerValidationError,
)

logger = logging.getLogger(__name__)

# Pattern to validate ticker format (1-10 alphanumeric characters with optional '.' or '-')
TICKER_REGEX = re.compile(r"^[A-Z0-9.\-]{1,10}$")

ANNUAL_FORM_TYPES = ("10-K", "10-K/A")


def normalize_and_validate_ticker(ticker: str) -> str:
    """Normalize and validate a stock ticker symbol.

    Args:
        ticker: Raw stock ticker symbol.

    Returns:
        Clean uppercase ticker string.

    Raises:
        TickerValidationError: If ticker is empty, whitespace, or invalid format.
    """
    if not ticker or not ticker.strip():
        raise TickerValidationError("Ticker symbol cannot be empty.")

    normalized = ticker.strip().upper()
    if not TICKER_REGEX.match(normalized):
        raise TickerValidationError(
            f"Invalid ticker format '{ticker}'. Ticker must be 1 to 10 alphanumeric characters."
        )
    return normalized


class SECService:
    """Service for querying SEC EDGAR to identify companies and discover filings."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._custom_client = client is not None
        self._client = client or httpx.Client(
            timeout=self.settings.SEC_REQUEST_TIMEOUT,
            headers={
                "User-Agent": self.settings.SEC_USER_AGENT,
                "Accept-Encoding": "gzip, deflate",
            },
        )
        # In-memory caches for polite querying and fast lookup
        self._ticker_map_cache: Optional[Dict[str, Dict[str, str]]] = None
        self._submissions_cache: Dict[str, dict] = {}

    def close(self) -> None:
        """Close HTTP client if owned by this instance."""
        if not self._custom_client and self._client:
            self._client.close()

    def __enter__(self) -> "SECService":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def clear_cache(self) -> None:
        """Clear in-memory ticker and submissions caches."""
        self._ticker_map_cache = None
        self._submissions_cache.clear()

    @staticmethod
    def build_filing_url(cik: str, accession_number: str, primary_document: str) -> str:
        """Construct public HTTPS URL to the primary filing document on SEC EDGAR."""
        cik_numeric = str(int(cik))
        accession_clean = accession_number.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{cik_numeric}/{accession_clean}/{primary_document}"

    @staticmethod
    def build_filing_index_url(cik: str, accession_number: str) -> str:
        """Construct public HTTPS URL to the filing folder index on SEC EDGAR."""
        cik_numeric = str(int(cik))
        accession_clean = accession_number.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{cik_numeric}/{accession_clean}/{accession_number}-index.htm"

    def _get(self, url: str) -> dict:
        """Perform GET request to SEC EDGAR with robust error translation."""
        logger.debug("Requesting SEC URL: %s", url)
        try:
            response = self._client.get(url)
            if response.status_code == 429:
                logger.warning("SEC EDGAR rate limit exceeded for URL: %s", url)
                raise SECRateLimitError(
                    "SEC EDGAR rate limit exceeded (10 requests/second limit). Please retry shortly."
                )
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            return response.json()
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as err:
            logger.error("SEC EDGAR connection timeout for %s: %s", url, err)
            raise SECConnectionError(f"Connection timeout while communicating with SEC EDGAR: {err}") from err
        except httpx.ConnectError as err:
            logger.error("SEC EDGAR connection error for %s: %s", url, err)
            raise SECConnectionError(f"Unable to connect to SEC EDGAR: {err}") from err
        except httpx.HTTPStatusError as err:
            logger.error("SEC EDGAR HTTP error %s for %s", err.response.status_code, url)
            raise SECServiceError(f"SEC EDGAR returned HTTP error {err.response.status_code}: {err}") from err
        except (ValueError, TypeError) as err:
            logger.error("SEC EDGAR malformed response for %s: %s", url, err)
            raise SECServiceError(f"Malformed JSON response received from SEC EDGAR: {err}") from err
        except (SECServiceError, SECRateLimitError, SECConnectionError):
            raise
        except Exception as err:
            logger.error("Unexpected error querying SEC EDGAR for %s: %s", url, err)
            raise SECServiceError(f"Unexpected error communicating with SEC EDGAR: {err}") from err

    def load_ticker_mapping(self, force_refresh: bool = False) -> Dict[str, Dict[str, str]]:
        """Fetch and cache ticker-to-CIK mapping from SEC EDGAR.

        Returns:
            Dictionary mapping uppercase ticker to metadata dict {'cik': str, 'title': str}.
        """
        if self._ticker_map_cache is not None and not force_refresh:
            return self._ticker_map_cache

        url = f"{self.settings.SEC_FILES_BASE_URL}/company_tickers.json"
        logger.info("Fetching company ticker mapping from SEC EDGAR (%s)", url)
        raw_data = self._get(url)

        if not isinstance(raw_data, dict):
            raise SECServiceError("Malformed company ticker map format from SEC EDGAR.")

        mapping: Dict[str, Dict[str, str]] = {}
        for entry in raw_data.values():
            if not isinstance(entry, dict):
                continue
            ticker = entry.get("ticker")
            cik_str = entry.get("cik_str")
            title = entry.get("title")

            if ticker and cik_str is not None:
                norm_ticker = str(ticker).strip().upper()
                mapping[norm_ticker] = {
                    "cik": str(cik_str).zfill(10),
                    "company_name": str(title or norm_ticker).strip(),
                }

        self._ticker_map_cache = mapping
        logger.info("Cached %d company tickers from SEC EDGAR", len(mapping))
        return mapping

    def resolve_ticker_to_cik(self, ticker: str) -> Tuple[str, str]:
        """Resolve a stock ticker to a 10-digit CIK and official company name.

        Args:
            ticker: Normalized ticker symbol.

        Returns:
            Tuple of (10-digit CIK string, official company title).

        Raises:
            CompanyNotFoundError: If ticker cannot be resolved in SEC records.
        """
        mapping = self.load_ticker_mapping()
        if ticker in mapping:
            entry = mapping[ticker]
            return entry["cik"], entry["company_name"]

        # Attempt one refresh in case ticker was newly listed
        mapping = self.load_ticker_mapping(force_refresh=True)
        if ticker in mapping:
            entry = mapping[ticker]
            return entry["cik"], entry["company_name"]

        raise CompanyNotFoundError(
            f"Company with ticker '{ticker}' was not found in SEC EDGAR records."
        )

    def get_company_submissions(self, cik: str) -> dict:
        """Retrieve raw submissions metadata for a 10-digit CIK from SEC EDGAR."""
        cik_clean = cik.zfill(10)
        if cik_clean in self._submissions_cache:
            return self._submissions_cache[cik_clean]

        url = f"{self.settings.SEC_BASE_URL}/submissions/CIK{cik_clean}.json"
        logger.info("Fetching company submissions for CIK %s", cik_clean)
        data = self._get(url)

        if not data:
            raise CompanyNotFoundError(f"SEC submissions data not found for CIK {cik_clean}.")

        self._submissions_cache[cik_clean] = data
        return data

    def get_company_by_ticker(self, ticker: str) -> Company:
        """Identify a company and retrieve its official metadata.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL', 'msft').

        Returns:
            Structured Company domain model.
        """
        normalized_ticker = normalize_and_validate_ticker(ticker)
        cik, title_from_tickers = self.resolve_ticker_to_cik(normalized_ticker)
        submissions = self.get_company_submissions(cik)

        company_name = submissions.get("name") or title_from_tickers
        sic = submissions.get("sic")
        sic_desc = submissions.get("sicDescription")

        # Primary exchange (if provided in exchanges array)
        exchanges = submissions.get("exchanges", [])
        exchange = exchanges[0] if (isinstance(exchanges, list) and exchanges) else None

        return Company(
            ticker=normalized_ticker,
            company_name=company_name,
            cik=cik,
            exchange=exchange,
            sic=str(sic) if sic is not None else None,
            sic_description=sic_desc,
        )

    def get_company_filings(
        self,
        ticker: str,
        form_types: Tuple[str, ...] = ANNUAL_FORM_TYPES,
    ) -> CompanyFilingsResponse:
        """Discover relevant annual filings (10-K, 10-K/A) for a company.

        Args:
            ticker: Stock ticker symbol.
            form_types: Tuple of form designations to include. Defaults to 10-K and 10-K/A.

        Returns:
            CompanyFilingsResponse containing company info and list of SECFiling models.
        """
        company = self.get_company_by_ticker(ticker)
        submissions = self.get_company_submissions(company.cik)

        filings_block = submissions.get("filings", {})
        recent = filings_block.get("recent", {})

        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        if not isinstance(forms, list) or not isinstance(accessions, list):
            raise SECServiceError(f"Malformed filing metadata array received for {company.ticker}.")

        matched_filings: List[SECFiling] = []
        n_items = min(len(forms), len(accessions), len(filing_dates), len(primary_docs))

        for i in range(n_items):
            form_type = str(forms[i]).strip()
            if form_type not in form_types:
                continue

            accession_number = str(accessions[i]).strip()
            filing_date = str(filing_dates[i]).strip()
            report_date = (
                str(report_dates[i]).strip()
                if (i < len(report_dates) and report_dates[i])
                else None
            )
            primary_document = str(primary_docs[i]).strip()

            if not accession_number or not primary_document or not filing_date:
                logger.warning("Skipping incomplete filing entry at index %d for %s", i, company.ticker)
                continue

            # Determine fiscal year from report date or filing date
            fiscal_year: Optional[int] = None
            date_to_use = report_date or filing_date
            if date_to_use and len(date_to_use) >= 4 and date_to_use[:4].isdigit():
                fiscal_year = int(date_to_use[:4])

            is_amendment = form_type.endswith("/A")

            filing = SECFiling(
                form_type=form_type,
                filing_date=filing_date,
                report_date=report_date,
                accession_number=accession_number,
                primary_document=primary_document,
                filing_url=self.build_filing_url(company.cik, accession_number, primary_document),
                filing_index_url=self.build_filing_index_url(company.cik, accession_number),
                fiscal_year=fiscal_year,
                is_amendment=is_amendment,
            )
            matched_filings.append(filing)

        logger.info(
            "Discovered %d relevant annual filings (%s) for %s",
            len(matched_filings),
            ", ".join(form_types),
            company.ticker,
        )

        return CompanyFilingsResponse(
            company=company,
            filings=matched_filings,
            total_count=len(matched_filings),
        )

    def get_latest_annual_filing(self, ticker: str) -> CompanyLatestFilingResponse:
        """Select the latest suitable annual filing (10-K or 10-K/A) for a company.

        Selection logic:
        1. Discovers all 10-K and 10-K/A filings.
        2. Raises FilingNotFoundError if no annual filings exist.
        3. Sorts filings primarily by fiscal reporting period (report_date),
           and secondarily by submission date (filing_date). This ensures:
           - The most recent reporting year is selected.
           - If an amendment (10-K/A) was submitted after the original 10-K for
             that period, the amendment is chosen as the prevailing record.

        Args:
            ticker: Stock ticker symbol.

        Returns:
            CompanyLatestFilingResponse containing company and latest SECFiling.
        """
        filings_resp = self.get_company_filings(ticker, form_types=ANNUAL_FORM_TYPES)
        filings = filings_resp.filings

        if not filings:
            raise FilingNotFoundError(
                f"No suitable annual filing (10-K or 10-K/A) found for company '{filings_resp.company.company_name}' ({filings_resp.company.ticker})."
            )

        # Sort descending: (effective period, filing date)
        # Empty report_date falls back to filing_date
        sorted_filings = sorted(
            filings,
            key=lambda f: (f.report_date or f.filing_date, f.filing_date),
            reverse=True,
        )

        latest_filing = sorted_filings[0]
        logger.info(
            "Selected latest annual filing for %s: %s (filed %s, report %s, accession %s)",
            filings_resp.company.ticker,
            latest_filing.form_type,
            latest_filing.filing_date,
            latest_filing.report_date,
            latest_filing.accession_number,
        )

        return CompanyLatestFilingResponse(
            company=filings_resp.company,
            filing=latest_filing,
        )


_service_instance: Optional[SECService] = None


def get_sec_service() -> SECService:
    """Dependency provider returning singleton SECService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SECService()
    return _service_instance
