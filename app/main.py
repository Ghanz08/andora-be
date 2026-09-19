from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.api.conversations import router as conversations_router
from app.api.health import router as health_router
from app.api.livekit import router as livekit_router
from app.api.routes.documents import router as documents_router


app = FastAPI(title="ANDORA Backend API", version="0.1.0")

allowed_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(livekit_router)
app.include_router(conversations_router)
app.mount("/tester", StaticFiles(directory="frontend", html=True), name="tester")
app.include_router(documents_router)
