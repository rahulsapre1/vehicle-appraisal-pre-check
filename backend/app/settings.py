from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Use environment variables (set by docker-compose env_file or system env)
    # For local development without Docker, create a .env file in the backend directory
    model_config = SettingsConfigDict(
        env_file=".env",  # Optional: only used for local dev without Docker
        env_file_encoding="utf-8", 
        extra="ignore"
    )

    # Supabase Configuration
    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_storage_bucket: str = Field(default="appraisal-artifacts", alias="SUPABASE_STORAGE_BUCKET")

    # OpenAI Configuration
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_vision_model: str = Field(default="gpt-4o-mini", alias="OPENAI_VISION_MODEL")
    openai_text_model: str = Field(default="gpt-4o-mini", alias="OPENAI_TEXT_MODEL")
    openai_request_timeout_seconds: int = Field(default=120, alias="OPENAI_REQUEST_TIMEOUT_SECONDS")

    # Features
    enable_rag: bool = Field(default=True, alias="ENABLE_RAG")

    # Render-specific
    port: int = Field(default=10000, alias="PORT")
    signed_url_expiration: int = Field(default=3600, alias="SIGNED_URL_EXPIRATION")
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")

    # Agent configuration
    agent_max_iterations: int = Field(default=50, alias="AGENT_MAX_ITERATIONS")
    agent_execution_timeout_seconds: int = Field(default=300, alias="AGENT_EXECUTION_TIMEOUT_SECONDS")

    @field_validator('supabase_url')
    @classmethod
    def validate_supabase_url(cls, v: str) -> str:
        """Validate Supabase URL format."""
        if not v:
            raise ValueError('SUPABASE_URL is required')
        if not v.startswith('https://'):
            raise ValueError('SUPABASE_URL must be a valid HTTPS URL')
        return v

    @field_validator('openai_api_key')
    @classmethod
    def validate_openai_key(cls, v: str) -> str:
        """Validate OpenAI API key format."""
        if not v:
            raise ValueError('OPENAI_API_KEY is required')
        if not v.startswith('sk-'):
            raise ValueError('OPENAI_API_KEY must start with "sk-"')
        return v


_settings_instance: Settings | None = None


def get_settings() -> Settings:
    """Get settings singleton instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
