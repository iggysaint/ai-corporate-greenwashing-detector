"""Domain exceptions for AI Corporate Greenwashing Detector."""


class GreenwashingDetectorError(Exception):
    """Base exception for all application domain errors."""


class TickerValidationError(GreenwashingDetectorError):
    """Raised when a ticker symbol is empty or fails format validation."""


class CompanyNotFoundError(GreenwashingDetectorError):
    """Raised when a company cannot be found for the given ticker in SEC records."""


class FilingNotFoundError(GreenwashingDetectorError):
    """Raised when no suitable filings (e.g., 10-K) are found for a company."""


class SECServiceError(GreenwashingDetectorError):
    """Raised when external SEC EDGAR requests fail or return unexpected data."""


class SECConnectionError(SECServiceError):
    """Raised when SEC EDGAR is unreachable or times out."""


class SECRateLimitError(SECServiceError):
    """Raised when SEC EDGAR returns HTTP 429 rate limit."""


class DocumentRetrievalError(SECServiceError):
    """Raised when an SEC filing document cannot be retrieved from SEC Archives."""


class DocumentParsingError(GreenwashingDetectorError):
    """Raised when document HTML content fails parsing or extraction."""


class ClaimNotFoundError(GreenwashingDetectorError):
    """Raised when a specific claim ID cannot be found."""


class EvidenceNotFoundError(GreenwashingDetectorError):
    """Raised when evidence cannot be found for a specific claim ID."""


class EvaluationNotFoundError(GreenwashingDetectorError):
    """Raised when an evaluation cannot be found for a specific claim ID."""


class LLMServiceError(GreenwashingDetectorError):
    """Base error for LLM evaluation service operations."""


class LLMProviderError(LLMServiceError):
    """Raised when external LLM provider API call fails or times out."""


class LLMOutputValidationError(LLMServiceError):
    """Raised when LLM response fails validation (e.g., hallucinated IDs, malformed JSON)."""


class SecurityValidationError(GreenwashingDetectorError):
    """Raised when an external resource or URL fails security validation."""


class SSRFSecurityError(SecurityValidationError):
    """Raised when an external request targets private, local, or restricted network ranges."""

