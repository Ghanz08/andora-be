from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    WHISPER_MODEL: str = "small"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_LANGUAGE: str = "id"
    LIVEKIT_TTS_MODEL: str = "cartesia/sonic-3"
    LIVEKIT_TTS_VOICE: str = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"

    NINEROUTER_BASE_URL: str = "http://127.0.0.1:20128/v1"
    NINEROUTER_API_KEY: str = ""
    NINEROUTER_MODEL: str = "ghn-fast"
    NINEROUTER_MAX_TOKENS: int = 2048
    OPENAI_API_KEY: str = ""

    MAX_CONTEXT_MESSAGES: int = 20


settings = Settings()
