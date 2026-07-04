from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTDIFF_", extra="ignore")

    database_url: str = "postgresql+asyncpg://agentdiff:agentdiff@localhost:5432/agentdiff"
    redis_url: str = "redis://localhost:6379"
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    # 32-byte urlsafe base64 Fernet key (or comma-separated keys) for encrypting Slack tokens at rest.
    secret_encryption_key: str = ""

    # Body-size cap (default 50 MB).
    max_body_bytes: int = 52_428_800

    # Rate limiting: POST /v1/runs per project per minute.
    rate_limit_runs_per_minute: int = 60

    # Rate limiting: POST /v1/traffic per project per minute.
    rate_limit_traffic_per_minute: int = 600

    # Drift detection settings.
    drift_window_minutes: int = 1440  # 24h windows compare day-over-day behavior; at typical agent traffic a 60-min window rarely reaches min_samples and makes drift appear broken
    drift_min_samples: int = 10
    drift_check_interval_minutes: int = 5

    # LLM explanation (optional — absent key leaves rule-based explanation intact).
    # Maps to AGENTDIFF_ANTHROPIC_API_KEY in the environment.
    anthropic_api_key: str = ""
    # Model override; leave empty to use the LLMClient default (claude-3-5-haiku-20241022).
    llm_model: str = ""

    # CORS: comma-separated allowed origins.
    cors_origins: str = "http://localhost:5173"

    # Slack OAuth (platform-level app — owner registers once).
    slack_client_id: str = ""
    slack_client_secret: str = ""
    # Slack requires an HTTPS redirect URL in production; for local dev use an
    # ngrok/cloudflared tunnel pointing to :8000.
    slack_redirect_url: str = "http://localhost:8000/v1/slack/callback"
    dashboard_url: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
