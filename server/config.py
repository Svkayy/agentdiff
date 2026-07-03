from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTDIFF_", extra="ignore")

    database_url: str = "postgresql+asyncpg://agentdiff:agentdiff@localhost:5432/agentdiff"
    redis_url: str = "redis://localhost:6379"
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    # 32-byte urlsafe base64 Fernet key for encrypting Slack tokens at rest.
    secret_encryption_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
