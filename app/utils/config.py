"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings for AI Corporate Greenwashing Detector."""

    # Application settings
    APP_NAME: str = "AI Corporate Greenwashing Detector"
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_PREFIX: str = "/api"

    # SEC EDGAR Integration
    SEC_USER_AGENT: str = "AI Corporate Greenwashing Detector (mr.ignatiusarthur@gmail.com)"
    SEC_REQUEST_TIMEOUT: float = 30.0
    SEC_BASE_URL: str = "https://data.sec.gov"
    SEC_FILES_BASE_URL: str = "https://www.sec.gov/files"
    SEC_ARCHIVES_BASE_URL: str = "https://www.sec.gov/Archives/edgar/data"

    # Document Ingestion & Passage Retrieval Configuration
    DOCUMENT_CACHE_IN_MEMORY: bool = True
    DOCUMENT_PERSIST_RAW: bool = False
    DEFAULT_ESG_KEYWORDS: list[str] = [
        # Environmental
        "emissions", "greenhouse gas", "ghg", "carbon", "climate", "renewable energy",
        "energy", "water", "waste", "recycling", "sustainability", "net zero",
        "decarbonization", "environmental",
        # Social
        "employees", "workforce", "diversity", "inclusion", "health and safety",
        "human rights", "community",
        # Governance
        "board", "governance", "ethics", "compliance", "risk management",
    ]

    # LLM Provider Configuration
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-4o"
    LLM_TIMEOUT: float = 30.0
    LLM_TEMPERATURE: float = 0.0
    EVALUATION_CACHE_IN_MEMORY: bool = True

    # Scoring Engine Configuration (rationale documented in docs/ESG_INTEGRITY_SCORE_METHODOLOGY.md)
    SCORE_WEIGHT_ENVIRONMENTAL: float = 0.40
    SCORE_WEIGHT_SOCIAL: float = 0.35
    SCORE_WEIGHT_GOVERNANCE: float = 0.25
    SCORING_METHODOLOGY_VERSION: str = "1.0.0"
    # Minimum assessable (non-insufficient-evidence, E/S/G-mapped) claims before an overall score is produced
    SCORE_MIN_ASSESSABLE_CLAIMS: int = 3
    # Low-materiality claims (weight below threshold) may hold at most this share of a pillar's weight
    SCORE_LOW_MATERIALITY_THRESHOLD: float = 1.0
    SCORE_LOW_MATERIALITY_MAX_SHARE: float = 0.25
    # Confidence is capped at MEDIUM when every evaluation is rule-based (keyword heuristics, not reading comprehension)
    SCORE_CAP_CONFIDENCE_FOR_RULE_BASED: bool = True

    # Future Database Integration
    DATABASE_URL: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of application settings."""
    return Settings()


settings = get_settings()
