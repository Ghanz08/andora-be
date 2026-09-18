from fastapi import Header, HTTPException, status

from app.config import settings
from app.integrations.supabase_client import SupabaseService
from app.schemas import UserAuth


async def get_current_user(authorization: str | None = Header(None)) -> UserAuth:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = authorization.split(" ")[1]

    user_data = SupabaseService.get_user_from_token(token)
    if user_data:
        return UserAuth(id=user_data["id"], email=user_data.get("email"))

    if settings.APP_ENV == "development" and (
        token.startswith("test-") or token == "mock-token"
    ):
        return UserAuth(id=token, email=f"{token}@andora.id")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
    )

