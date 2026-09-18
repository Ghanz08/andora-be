from datetime import timedelta
from livekit import api
from app.config import settings


class LiveKitService:
    def __init__(self):
        self.url = settings.LIVEKIT_URL
        self.api_key = settings.LIVEKIT_API_KEY
        self.api_secret = settings.LIVEKIT_API_SECRET

    def create_user_token(
        self,
        user_id: str,
        user_name: str | None = None,
        room_name: str | None = None,
        ttl_minutes: int = 15,
    ) -> str:
        if not self.url or not self.api_key or not self.api_secret:
            raise RuntimeError("LiveKit credentials are not configured")

        if not room_name:
            room_name = f"andora-{user_id}"

        token = (
            api.AccessToken(self.api_key, self.api_secret)
            .with_identity(user_id)
            .with_name(user_name or "User")
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                )
            )
            .with_ttl(timedelta(minutes=ttl_minutes))
        )
        return token.to_jwt()


livekit_service = LiveKitService()
