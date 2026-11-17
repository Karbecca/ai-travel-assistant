from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Travel Assistant"
    database_url: str = "sqlite:///./ai_travel_assistant.db"
    jwt_secret_key: str = "change-me-in-production-use-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    anthropic_temperature: float = 0.7
    anthropic_max_tokens: int = 2000
    llm_max_retries: int = 2
    weather_api_key: str = ""
    opentripmap_api_key: str = ""
    vector_store_path: str = "./vector_store"
    dd_agent_host: str = "localhost"
    dd_statsd_port: int = 8125
    dd_service: str = "ai-travel-assistant"
    dd_env: str = "development"
    guardrail_max_input_length: int = 2000
    guardrail_min_days: int = 1
    guardrail_max_days: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
