from livekit.plugins import google

from app.agent.prompt import SYSTEM_PROMPT
from app.config import settings


def create_realtime_model():
    return google.realtime.RealtimeModel(
        model=settings.GEMINI_REALTIME_MODEL,
        voice=settings.GEMINI_REALTIME_VOICE,
        api_key=settings.GOOGLE_API_KEY or None,
        temperature=settings.GEMINI_REALTIME_TEMPERATURE,
        instructions=SYSTEM_PROMPT,
    )
