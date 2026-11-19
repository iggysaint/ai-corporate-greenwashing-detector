"""Main entry point for AI Corporate Greenwashing Detector FastAPI application."""

from typing import Dict
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.company_routes import router as company_router
from app.api.evaluation_routes import router as evaluation_router
from app.api.evidence_routes import router as evidence_router
from app.api.gse_routes import router as gse_router
from app.utils.config import settings
from app.services.gse_service import (
    GSECompanyNotFoundError,
    GSEConnectionError,
    GSEDocumentParsingError,
    GSEDocumentRetrievalError,
    GSEServiceError,
)
from app.utils.exceptions import (
    ClaimNotFoundError,
    CompanyNotFoundError,
    DocumentParsingError,
    DocumentRetrievalError,
    EvaluationNotFoundError,
    EvidenceNotFoundError,
    FilingNotFoundError,
    LLMOutputValidationError,
    LLMProviderError,
    LLMServiceError,
    SECConnectionError,
    SECRateLimitError,
    SECServiceError,
    SecurityValidationError,
    SSRFSecurityError,
    TickerValidationError,
)

app = FastAPI(
    title=settings.APP_NAME,
    description="Analytical platform for evaluating corporate sustainability claims against SEC filings, Ghana Stock Exchange disclosures, and public corporate reports.",
    version="0.7.0",
)


# Exception Handlers
@app.exception_handler(TickerValidationError)
def ticker_validation_handler(request: Request, exc: TickerValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "error": "invalid_ticker"},
    )


@app.exception_handler(CompanyNotFoundError)
def company_not_found_handler(request: Request, exc: CompanyNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "error": "company_not_found"},
    )


@app.exception_handler(FilingNotFoundError)
def filing_not_found_handler(request: Request, exc: FilingNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "error": "filing_not_found"},
    )


@app.exception_handler(SECRateLimitError)
def sec_rate_limit_handler(request: Request, exc: SECRateLimitError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc), "error": "sec_rate_limit"},
    )


@app.exception_handler(SECConnectionError)
def sec_connection_handler(request: Request, exc: SECConnectionError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc), "error": "sec_connection_error"},
    )


@app.exception_handler(SECServiceError)
def sec_service_handler(request: Request, exc: SECServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": str(exc), "error": "sec_service_error"},
    )


@app.exception_handler(DocumentRetrievalError)
def document_retrieval_handler(request: Request, exc: DocumentRetrievalError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": str(exc), "error": "document_retrieval_error"},
    )


@app.exception_handler(DocumentParsingError)
def document_parsing_handler(request: Request, exc: DocumentParsingError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc), "error": "document_parsing_error"},
    )


@app.exception_handler(ClaimNotFoundError)
def claim_not_found_handler(request: Request, exc: ClaimNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "error": "claim_not_found"},
    )


@app.exception_handler(EvidenceNotFoundError)
def evidence_not_found_handler(request: Request, exc: EvidenceNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "error": "evidence_not_found"},
    )


@app.exception_handler(EvaluationNotFoundError)
def evaluation_not_found_handler(request: Request, exc: EvaluationNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "error": "evaluation_not_found"},
    )


@app.exception_handler(LLMProviderError)
def llm_provider_handler(request: Request, exc: LLMProviderError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": str(exc), "error": "llm_provider_error"},
    )


@app.exception_handler(LLMOutputValidationError)
def llm_output_validation_handler(request: Request, exc: LLMOutputValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc), "error": "llm_output_validation_error"},
    )


@app.exception_handler(LLMServiceError)
def llm_service_handler(request: Request, exc: LLMServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc), "error": "llm_service_error"},
    )


@app.exception_handler(SSRFSecurityError)
def ssrf_security_handler(request: Request, exc: SSRFSecurityError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc), "error": "ssrf_security_violation"},
    )


@app.exception_handler(SecurityValidationError)
def security_validation_handler(request: Request, exc: SecurityValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "error": "security_validation_error"},
    )


# ── GSE Exception Handlers ──────────────────────────────

@app.exception_handler(GSECompanyNotFoundError)
def gse_company_not_found_handler(request: Request, exc: GSECompanyNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "error": "gse_company_not_found"},
    )


@app.exception_handler(GSEConnectionError)
def gse_connection_handler(request: Request, exc: GSEConnectionError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc), "error": "gse_connection_error"},
    )


@app.exception_handler(GSEDocumentRetrievalError)
def gse_document_retrieval_handler(request: Request, exc: GSEDocumentRetrievalError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": str(exc), "error": "gse_document_retrieval_error"},
    )


@app.exception_handler(GSEDocumentParsingError)
def gse_document_parsing_handler(request: Request, exc: GSEDocumentParsingError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc), "error": "gse_document_parsing_error"},
    )


@app.exception_handler(GSEServiceError)
def gse_service_handler(request: Request, exc: GSEServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": str(exc), "error": "gse_service_error"},
    )


# Routers
app.include_router(company_router, prefix="/api/v1")
app.include_router(evidence_router, prefix="/api/v1")
app.include_router(evaluation_router, prefix="/api/v1")
app.include_router(gse_router, prefix="/api/v1")


# System Endpoints
@app.get("/health", summary="Health Check", tags=["System"])
def health_check() -> Dict[str, str]:
    """Return health status of the application."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
    }
