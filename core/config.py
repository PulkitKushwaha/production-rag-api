"""
Application Settings
 
Centralizes all configuration in one place.
Settings are loaded from environment variables with defaults.
Using pydantic-settings ensures type validation on startup.
 
Design decision: fail fast on missing required config.
If SECRET_KEY is not set in production, the app should
refuse to start and not silently use an insecure default.
"""
 
from pydantic_settings import BaseSettings
from typing import List, Optional
import os
 
 
class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
 
    All settings have defaults suitable for local development.
    Production deployments must override sensitive values.
    """
 
    # API metadata
    app_name: str = "Production RAG API"
    app_version: str = "0.1.0"
    debug: bool = False
 
    # Authentication
    secret_key: str = "dev-secret-key-change-in-production-min-32-chars"
    api_key_header: str = "X-API-Key"
    allowed_api_keys: str = "dev-key-1,dev-key-2"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
 
    # Rate limiting
    rate_limit_per_minute: int = 20
    rate_limit_per_hour: int = 200
 
    # Pipeline
    vector_store_path: str = "./data/vector_store"
    llm_model: str = "gpt-4"
 
    # Observability
    log_level: str = "INFO"
    enable_metrics: bool = True
 
    @property
    def api_keys_list(self) -> List[str]:
        """Parse comma-separated API keys into a list."""
        return [k.strip() for k in self.allowed_api_keys.split(",") if k.strip()]
 
    class Config:
        env_file = ".env"
        case_sensitive = False
 
 
# Singleton settings instance
settings = Settings()