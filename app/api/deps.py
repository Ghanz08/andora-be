from fastapi import Header, HTTPException, status
import asyncio

from app.integrations.supabase_client import SupabaseService
from app.schemas import UserAuth


async def get_current_user(authorization: str | None = Header(None)) -> UserAuth:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = authorization.split(" ")[1]

    try:
        user_data = await asyncio.to_thread(SupabaseService.get_user_from_token, token)
    except ValueError:
        user_data = None
    if user_data:
        return UserAuth(id=user_data["id"], email=user_data.get("email"))

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
    )
