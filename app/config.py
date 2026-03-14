from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/postgres"

    # Twilio (master account credentials — shared across all tenants)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""

    # OpenAI
    openai_api_key: str = ""
    openai_realtime_model: str = "gpt-4o-mini-realtime-preview"
    openai_realtime_voice: str = "coral"

    # Supabase
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_anon_key: str = ""
    enable_auth_debug_endpoint: bool = False

    # Server
    server_url: str = "http://localhost:8000"
    call_inactivity_timeout_s: int = 30

    # Redis (for dashboard pub/sub)
    redis_url: str = "redis://localhost:6379"
    tenant_runtime_refresh_interval_s: int = 5

    @field_validator("supabase_url", "supabase_anon_key", mode="before")
    @classmethod
    def validate_required_supabase_fields(cls, value: str, info):
        cleaned = (value or "").strip()
        placeholder_map = {
            "supabase_url": "https://your-project.supabase.co",
            "supabase_anon_key": "your-anon-key",
        }
        placeholder = placeholder_map.get(info.field_name)
        if not cleaned or (placeholder and cleaned == placeholder):
            raise ValueError(
                f"{info.field_name.upper()} must be set in .env for Supabase auth integration"
            )
        return cleaned

    @field_validator("supabase_jwt_secret", mode="before")
    @classmethod
    def validate_supabase_jwt_secret(cls, value: str):
        cleaned = (value or "").strip()
        if cleaned == "your-jwt-secret":
            return ""
        return cleaned

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
