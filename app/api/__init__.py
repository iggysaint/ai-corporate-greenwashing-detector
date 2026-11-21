"""API routing and endpoint controllers."""

from app.api.company_routes import router as company_router
from app.api.evaluation_routes import router as evaluation_router
from app.api.evidence_routes import router as evidence_router
from app.api.gse_routes import router as gse_router
from app.api.scoring_routes import router as scoring_router

__all__ = ["company_router", "evidence_router", "evaluation_router", "gse_router", "scoring_router"]

