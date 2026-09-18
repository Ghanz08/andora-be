from fastapi import FastAPI
from app.api.conversations import router as conversations_router
from app.api.health import router as health_router
from app.api.livekit import router as livekit_router

app = FastAPI(title="ANDORA Backend API", version="0.1.0")

app.include_router(health_router)
app.include_router(livekit_router)
app.include_router(conversations_router)

