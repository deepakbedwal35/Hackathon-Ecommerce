import sys
from typing import Any, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    DATABASE_URL: str = Field(default=..., description="PostgreSQL database URL")
    JWT_SECRET: str = Field(default=..., description="Secret key for JWT verification")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    RETURN_WINDOW_DAYS: int = 30
    AUTO_REFUND_LIMIT: str = "5000.00"
    PAYMENT_MOCK_MODE: str = "ok"
    NON_RETURNABLE_CATEGORIES: list[str] = ["grocery"]
    LLM_PROVIDER: str = "gemini"
    LLM_API_KEY: str = Field(default="", description="API key for LLM provider")
    LLM_MODEL: str = "gemini-1.5-flash"
    LLM_TIMEOUT_SECONDS: int = 20
    CORS_ORIGINS: Union[list[str], str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    LOG_LEVEL: str = "INFO"

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "DATABASE_URL is required and cannot be empty. Please set DATABASE_URL."
            )
        return v.strip()

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if not v or len(v.strip()) < 32:
            raise ValueError(
                "JWT_SECRET is required and must be at least 32 characters long."
            )
        return v.strip()

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                import json
                return json.loads(v)
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return v
        return []


def load_settings() -> Settings:
    try:
        return Settings()
    except Exception as exc:
        exc_str = str(exc)
        if "DATABASE_URL" in exc_str:
            sys.stderr.write(
                "\n=======================================================\n"
                "CRITICAL CONFIGURATION ERROR:\n"
                "DATABASE_URL is missing or empty!\n"
                "Please configure DATABASE_URL in your environment or .env file.\n"
                "=======================================================\n\n"
            )
            raise RuntimeError(
                "CRITICAL CONFIG ERROR: DATABASE_URL is required and missing."
            ) from exc
        if "JWT_SECRET" in exc_str:
            sys.stderr.write(
                "\n=======================================================\n"
                "CRITICAL CONFIGURATION ERROR:\n"
                "JWT_SECRET is missing or shorter than 32 characters!\n"
                "Please configure JWT_SECRET in your environment or .env file.\n"
                "=======================================================\n\n"
            )
            raise RuntimeError(
                "CRITICAL CONFIG ERROR: JWT_SECRET is required and must be at least 32 characters."
            ) from exc
        raise


settings = load_settings()
