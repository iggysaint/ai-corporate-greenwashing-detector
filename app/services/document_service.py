"""SEC 10-K Document Retrieval, HTML Processing, and Section Extraction Service."""

import logging
import re
import warnings
from typing import Dict, List, Optional, Set, Tuple
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import httpx

from app.models.document import Document, DocumentSection, RelevantPassage
from app.models.filing import SECFiling
from app.utils.config import Settings, get_settings
from app.utils.exceptions import (
    DocumentParsingError,
    DocumentRetrievalError,
    SECConnectionError,
    SECRateLimitError,
    SECServiceError,
)

logger = logging.getLogger(__name__)

# Suppress XML-as-HTML parsing warnings emitted by BeautifulSoup for SEC XML/iXBRL filings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Standard 10-K Item classification mapping
SECTION_TYPE_MAP = {
    "item_1": "business",
    "item_1a": "risk_factors",
    "item_1b": "staff_comments",
    "item_1c": "cybersecurity",
    "item_2": "properties",
    "item_3": "legal_proceedings",
    "item_4": "mine_safety",
    "item_5": "market_equity",
    "item_6": "financial_data",
    "item_7": "mda",
    "item_7a": "market_risk",
    "item_8": "financials",
    "item_9": "accountant_changes",
    "item_9a": "controls_procedures",
    "item_9b": "other_info",
    "item_9c": "foreign_jurisdictions",
    "item_10": "governance",
    "item_11": "executive_compensation",
    "item_12": "security_ownership",
    "item_13": "related_transactions",
    "item_14": "accountant_fees",
    "item_15": "exhibits",
    "item_16": "summary",
}

# Regex matching 10-K Item headers across common formatting variations
ITEM_HEADER_PATTERN = re.compile(
    r"(?i)(?:^|\n)\s*(ITEM\s+(?:1[0-6]|[1-9])[A-Z]?)\s*[:.\-—–]?\s*([^\n\r]{2,120})",
    re.MULTILINE,
)


class DocumentService:
    """Service for retrieving, cleaning, and extracting sections/passages from SEC filings."""

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
        # In-memory document cache keyed by accession_number
        self._document_cache: Dict[str, Document] = {}

    def close(self) -> None:
        """Close HTTP client if owned by this instance."""
        if not self._custom_client and self._client:
            self._client.close()

    def __enter__(self) -> "DocumentService":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def clear_cache(self) -> None:
        """Clear in-memory document cache."""
        self._document_cache.clear()

    def retrieve_raw_document(self, url: str) -> str:
        """Retrieve raw HTML filing document from SEC EDGAR Archives.

        Args:
            url: Public HTTPS URL to the filing on SEC EDGAR.

        Returns:
            Raw HTML document string.

        Raises:
            SECRateLimitError: On HTTP 429 rate limit.
            DocumentRetrievalError: On HTTP 404 or other HTTP error.
            SECConnectionError: On timeout or network failure.
        """
        logger.info("Retrieving SEC filing document from: %s", url)
        try:
            response = self._client.get(url)
            if response.status_code == 429:
                logger.warning("SEC EDGAR rate limit encountered for document: %s", url)
                raise SECRateLimitError(
                    "SEC EDGAR rate limit exceeded (10 requests/second). Please retry shortly."
                )
            if response.status_code == 404:
                logger.error("SEC filing document not found at: %s", url)
                raise DocumentRetrievalError(f"SEC filing document not found at: {url}")
            response.raise_for_status()
            return response.text
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as err:
            logger.error("Timeout retrieving SEC document from %s: %s", url, err)
            raise SECConnectionError(f"Connection timeout while retrieving SEC document: {err}") from err
        except httpx.ConnectError as err:
            logger.error("Connection error retrieving SEC document from %s: %s", url, err)
            raise SECConnectionError(f"Unable to connect to SEC EDGAR Archives: {err}") from err
        except httpx.HTTPStatusError as err:
            logger.error("HTTP error %s retrieving SEC document from %s", err.response.status_code, url)
            raise DocumentRetrievalError(
                f"SEC EDGAR Archives returned HTTP {err.response.status_code}: {err}"
            ) from err
        except (SECRateLimitError, DocumentRetrievalError, SECConnectionError):
            raise
        except Exception as err:
            logger.error("Unexpected error retrieving SEC document from %s: %s", url, err)
            raise DocumentRetrievalError(f"Failed to retrieve SEC filing document: {err}") from err

    def clean_and_normalize_html(self, html_content: str) -> Tuple[str, Optional[str]]:
        """Clean HTML and normalize text while strictly preserving numbers and punctuation.

        Removes scripts, styles, metadata, navigation, and excessive blank lines.
        Converts tables to structured rows to maintain financial figure context.

        Args:
            html_content: Raw HTML content.

        Returns:
            Tuple of (cleaned_text, document_title).

        Raises:
            DocumentParsingError: If HTML parsing fails completely.
        """
        if not html_content or not html_content.strip():
            raise DocumentParsingError("Document HTML content is empty.")

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
            try:
                soup = BeautifulSoup(html_content, "lxml")
            except Exception as err:
                logger.error("HTML parser error: %s", err)
                raise DocumentParsingError(f"Failed to parse HTML document: {err}") from err

        # Extract title if present
        title: Optional[str] = None
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # Remove scripts, styles, metadata, and non-printable elements
        for element in soup(["script", "style", "noscript", "meta", "link", "header", "footer"]):
            element.decompose()

        # Format tables to retain tabular numeric context
        for table in soup.find_all("table"):
            table_rows = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if any(cells):
                    table_rows.append(" | ".join(cells))
            if table_rows:
                table_text = "\n" + "\n".join(table_rows) + "\n"
                table.replace_with(table_text)

        # Extract plain text
        raw_text = soup.get_text(separator="\n")

        # Text normalization:
        # 1. Replace non-breaking spaces and Unicode whitespace variants with standard space
        normalized = raw_text.replace("\xa0", " ").replace("\u200b", "")

        # 2. Normalize whitespace on each line without altering numbers, currencies, or symbols
        cleaned_lines = []
        for line in normalized.splitlines():
            line_stripped = re.sub(r"[ \t]+", " ", line).strip()
            if line_stripped:
                cleaned_lines.append(line_stripped)
            else:
                cleaned_lines.append("")

        # 3. Collapse 3+ consecutive newlines to double newlines (paragraphs)
        collapsed = "\n".join(cleaned_lines)
        cleaned_text = re.sub(r"\n{3,}", "\n\n", collapsed).strip()

        return cleaned_text, title

    def detect_sections(self, text: str) -> List[DocumentSection]:
        """Detect and segment standard SEC 10-K sections from normalized text.

        Distinguishes substantive body sections from Table of Contents (TOC) references
        by grouping occurrences of each Item header and selecting the prevailing body section.

        Args:
            text: Normalized document plain text.

        Returns:
            List of structured DocumentSection instances.
        """
        if not text:
            return []

        all_matches = list(ITEM_HEADER_PATTERN.finditer(text))

        if not all_matches:
            logger.info("No standard 10-K Item headings detected; defaulting to full document section.")
            return [
                DocumentSection(
                    section_id="full_document",
                    section_title="Full Document",
                    section_type="other",
                    text=text,
                    start_position=0,
                    end_position=len(text),
                    word_count=len(text.split()),
                )
            ]

        # In SEC filings, Table of Contents entries precede the actual body sections.
        # Discard entries containing dot leaders (e.g. ".... 1") and choose the last occurrence of each Item code.
        by_code: Dict[str, List[re.Match]] = {}
        for m in all_matches:
            code = re.sub(r"\s+", "_", m.group(1).lower())
            desc = m.group(2).strip()
            if re.search(r"\.{3,}", desc):
                continue
            by_code.setdefault(code, []).append(m)

        body_matches = [occurrences[-1] for occurrences in by_code.values()]
        body_matches.sort(key=lambda m: m.start())

        if not body_matches:
            body_matches = all_matches

        sections: List[DocumentSection] = []
        for i, match in enumerate(body_matches):
            raw_item_code = match.group(1).strip()
            # Normalize item code e.g. "ITEM 1A" -> "item_1a"
            norm_id = re.sub(r"\s+", "_", raw_item_code.lower())
            heading_desc = match.group(2).strip()
            section_title = f"{raw_item_code.title()}. {heading_desc}"

            start_pos = match.start()
            end_pos = body_matches[i + 1].start() if i + 1 < len(body_matches) else len(text)

            section_text = text[start_pos:end_pos].strip()
            section_type = SECTION_TYPE_MAP.get(norm_id, "other")
            word_count = len(section_text.split())

            sections.append(
                DocumentSection(
                    section_id=norm_id,
                    section_title=section_title,
                    section_type=section_type,
                    text=section_text,
                    start_position=start_pos,
                    end_position=end_pos,
                    word_count=word_count,
                )
            )

        logger.info("Successfully detected %d substantive 10-K sections", len(sections))
        return sections

    def process_document(
        self,
        filing: SECFiling,
        html_content: Optional[str] = None,
    ) -> Document:
        """Retrieve, clean, segment, and produce a structured Document representation.

        Results are cached in memory by accession_number to avoid repeated processing.

        Args:
            filing: SECFiling metadata from Phase 2.
            html_content: Optional raw HTML string (used for testing or pre-downloaded files).

        Returns:
            Structured Document model.
        """
        accession = filing.accession_number

        # Check in-memory cache
        if self.settings.DOCUMENT_CACHE_IN_MEMORY and accession in self._document_cache:
            logger.debug("Returning in-memory cached Document for accession %s", accession)
            return self._document_cache[accession]

        # Retrieve raw HTML if not supplied
        raw_html = html_content
        if raw_html is None:
            raw_html = self.retrieve_raw_document(filing.filing_url)

        # Parse and normalize HTML
        cleaned_text, title = self.clean_and_normalize_html(raw_html)
        word_count = len(cleaned_text.split())

        # Extract structured sections
        sections = self.detect_sections(cleaned_text)

        document = Document(
            accession_number=accession,
            form_type=filing.form_type,
            filing_date=filing.filing_date,
            report_date=filing.report_date,
            source_url=filing.filing_url,
            title=title or f"{filing.form_type} Annual Report",
            text=cleaned_text,
            word_count=word_count,
            sections=sections,
        )

        if self.settings.DOCUMENT_CACHE_IN_MEMORY:
            self._document_cache[accession] = document

        return document

    def find_relevant_passages(
        self,
        document: Document,
        company_ticker: str,
        keywords: Optional[List[str]] = None,
        max_passages: int = 50,
    ) -> List[RelevantPassage]:
        """Locate traceable passages matching keyword concepts with surrounding context.

        Every passage is deterministic and traced back to company, filing accession,
        source URL, section ID, section title, and character position.

        Args:
            document: Structured Document instance.
            company_ticker: Normalized stock ticker symbol.
            keywords: List of search keywords. Defaults to settings.DEFAULT_ESG_KEYWORDS.
            max_passages: Maximum passages to return (default 50).

        Returns:
            List of structured RelevantPassage models.
        """
        target_keywords = keywords or self.settings.DEFAULT_ESG_KEYWORDS
        if not target_keywords:
            return []

        # Prepare compiled regex patterns for whole-word / phrase matching
        compiled_patterns = [
            (kw, re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE))
            for kw in target_keywords
            if kw and kw.strip()
        ]

        relevant_passages: List[RelevantPassage] = []
        passage_counter = 0

        # Search within detected sections (or fallback to document text if no sections)
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
            # Break section text into paragraphs using double-newlines
            paragraphs = section.text.split("\n\n")
            current_offset = 0

            for para in paragraphs:
                para_clean = para.strip()
                if not para_clean:
                    current_offset += len(para) + 2
                    continue

                matched: List[str] = []
                for kw, pattern in compiled_patterns:
                    if pattern.search(para_clean):
                        matched.append(kw)

                if matched:
                    passage_counter += 1
                    passage_id = f"{document.accession_number}_{section.section_id}_p{passage_counter}"

                    # Keep passage text intact (or window if single paragraph is exceptionally massive)
                    passage_text = (
                        para_clean
                        if len(para_clean) <= 1200
                        else para_clean[:1200] + "... [truncated]"
                    )

                    passage = RelevantPassage(
                        passage_id=passage_id,
                        company_ticker=company_ticker,
                        accession_number=document.accession_number,
                        source_url=document.source_url,
                        section_id=section.section_id,
                        section_title=section.section_title,
                        text=passage_text,
                        matched_keywords=matched,
                        approximate_position=current_offset,
                    )
                    relevant_passages.append(passage)

                    if len(relevant_passages) >= max_passages:
                        logger.info(
                            "Reached maximum passages cap (%d) for %s",
                            max_passages,
                            company_ticker,
                        )
                        return relevant_passages

                current_offset += len(para) + 2

        logger.info(
            "Found %d relevant passages matching %d keyword concepts for %s",
            len(relevant_passages),
            len(target_keywords),
            company_ticker,
        )
        return relevant_passages


_document_service_instance: Optional[DocumentService] = None


def get_document_service() -> DocumentService:
    """Dependency provider returning singleton DocumentService instance."""
    global _document_service_instance
    if _document_service_instance is None:
        _document_service_instance = DocumentService()
    return _document_service_instance
