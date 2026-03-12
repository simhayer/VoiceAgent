from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/postgres"

    # Twilio (master account credentials — shared across all tenants)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""

    # Deepgram
    deepgram_api_key: str = ""
    deepgram_utterance_end_ms: int = 1000
    deepgram_endpointing_ms: int = 200
    stt_barge_in_min_chars: int = 3
    stt_barge_in_min_words: int = 1
    stt_barge_in_min_confidence: float = 0.45
    stt_barge_in_promotion_debounce_ms: int = 300
    stt_early_utterance_delay_ms: int = 400

    # Cartesia (default; tenants can override voice_id)
    cartesia_api_key: str = ""
    cartesia_voice_id: str = ""
    cartesia_speed: str = "normal"

    # OpenAI
    openai_api_key: str = ""

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # Server
    server_url: str = "http://localhost:8000"
    voice_state_machine_enabled: bool = True
    agent_stream_flush_ms: int = 180
    max_conversation_messages: int = 20
    call_inactivity_timeout_s: int = 30

    # Redis (for dashboard pub/sub)
    redis_url: str = "redis://localhost:6379"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
