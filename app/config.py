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

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # Server
    server_url: str = "http://localhost:8000"
    call_inactivity_timeout_s: int = 30

    # Redis (for dashboard pub/sub)
    redis_url: str = "redis://localhost:6379"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
