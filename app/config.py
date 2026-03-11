from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/postgres"

    # Office
    office_name: str = "Bright Smile Dental"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # Deepgram
    deepgram_api_key: str = ""
    deepgram_utterance_end_ms: int = 1000
    deepgram_endpointing_ms: int = 200
    stt_barge_in_min_chars: int = 3
    stt_barge_in_min_words: int = 1
    stt_barge_in_min_confidence: float = 0.45
    stt_barge_in_promotion_debounce_ms: int = 700

    # Cartesia
    cartesia_api_key: str = ""
    cartesia_voice_id: str = "694f9389-aac1-45b6-b726-9d9369183238"
    cartesia_speed: str = "normal"

    # OpenAI
    openai_api_key: str = ""

    # Server
    server_url: str = "http://localhost:8000"
    voice_state_machine_enabled: bool = True
    agent_stream_flush_ms: int = 180
    max_conversation_messages: int = 20
    call_inactivity_timeout_s: int = 30

    model_config = {"env_file": ".env"}


settings = Settings()
