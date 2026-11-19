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
