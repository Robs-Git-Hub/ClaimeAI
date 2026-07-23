from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


def _validate_openai_api_key(v: str | None) -> str | None:
    """Validate that the OpenAI API key starts with 'sk-proj-'."""
    if v and not v.startswith("sk-proj-"):
        raise ValueError("OpenAI API key must start with 'sk-proj-'")
    return v


def _validate_exa_api_key(v: str | None) -> str | None:
    """Validate that the Exa API key is a valid UUID4."""
    if v:
        try:
            UUID(v, version=4)
        except ValueError:
            raise ValueError("Exa API key must be a valid UUID4") from None
    return v


def _validate_tavily_api_key(v: str | None) -> str | None:
    """Validate that the Tavily API key starts with 'tvly-'."""
    if v and not v.startswith("tvly-"):
        raise ValueError("Tavily API key must start with 'tvly-'")
    return v


def _validate_openrouter_api_key(v: str | None) -> str | None:
    """Validate that the OpenRouter API key starts with 'sk-or-'."""
    if v and not v.startswith("sk-or-"):
        raise ValueError("OpenRouter API key must start with 'sk-or-'")
    return v


_ALLOWED_LLM_PROVIDERS = ("openai", "openrouter")


def _validate_llm_provider(v: str) -> str:
    """Normalize and validate the LLM provider selection."""
    normalized = v.strip().lower()
    if normalized not in _ALLOWED_LLM_PROVIDERS:
        raise ValueError(
            f"LLM_PROVIDER must be one of {_ALLOWED_LLM_PROVIDERS}, got '{v}'"
        )
    return normalized


OpenAIAPIKey = Annotated[str | None, AfterValidator(_validate_openai_api_key)]
ExaAPIKey = Annotated[str | None, AfterValidator(_validate_exa_api_key)]
TavilyAPIKey = Annotated[str | None, AfterValidator(_validate_tavily_api_key)]
OpenRouterAPIKey = Annotated[str | None, AfterValidator(_validate_openrouter_api_key)]
LLMProvider = Annotated[str, AfterValidator(_validate_llm_provider)]


class Settings(BaseSettings):
    """Manages application settings and environment variables."""

    llm_provider: LLMProvider = Field(default="openai", alias="LLM_PROVIDER")
    openai_api_key: OpenAIAPIKey = Field(default=None, alias="OPENAI_API_KEY")
    openrouter_api_key: OpenRouterAPIKey = Field(
        default=None, alias="OPENROUTER_API_KEY"
    )
    exa_api_key: ExaAPIKey = Field(default=None, alias="EXA_API_KEY")
    tavily_api_key: TavilyAPIKey = Field(default=None, alias="TAVILY_API_KEY")
    redis_uri: RedisDsn = Field(default="redis://localhost:6379", alias="REDIS_URL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


settings = Settings()
