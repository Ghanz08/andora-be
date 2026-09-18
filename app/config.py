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
    LIVEKIT_STT_MODEL: str = "deepgram/nova-3"
    LIVEKIT_STT_LANGUAGE: str = "id"
    LIVEKIT_STT_KEYTERMS: str = "beasiswa,Beasiswa Kaltim Tuntas,Kaltim Tuntas,Beasiswa Unggulan"
    LIVEKIT_TTS_MODEL: str = "cartesia/sonic-3"
    LIVEKIT_TTS_VOICE: str = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"

    NINEROUTER_BASE_URL: str = "http://127.0.0.1:20128/v1"
    NINEROUTER_API_KEY: str = ""
    NINEROUTER_MODEL: str = "ghn-fast"
    NINEROUTER_MAX_TOKENS: int = 2048
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    GEMINI_REALTIME_MODEL: str = "gemini-3.8-live"
    GEMINI_REALTIME_VOICE: str = "Puck"
    GEMINI_REALTIME_TEMPERATURE: float = 0.8

    MAX_CONTEXT_MESSAGES: int = 20


settings = Settings()
