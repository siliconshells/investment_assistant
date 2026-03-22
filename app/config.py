"""Centralized configuration loaded from environment variables."""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "info"

    # AWS
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "investment-assistant-data"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # LLM
    llm_provider: str = "openai"  # "openai" or "anthropic"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # External data
    alpha_vantage_api_key: str = "demo"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # This is the line that stops the crash
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
