from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./receptionist.db"

    # Office
    office_name: str = "Bright Smile Dental"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # Deepgram
    deepgram_api_key: str = ""

    # Cartesia
    cartesia_api_key: str = ""
    cartesia_voice_id: str = ""
    cartesia_speed: str = "normal"

    # OpenAI
    openai_api_key: str = ""

    # Server
    server_url: str = "http://localhost:8000"

    # Redis (for dashboard pub/sub)
    redis_url: str = "redis://localhost:6379"

    model_config = {"env_file": ".env"}


settings = Settings()
