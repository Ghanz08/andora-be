from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.conversations import router as conversations_router
from app.api.health import router as health_router
from app.api.livekit import router as livekit_router
from app.api.routes.documents import router as documents_router


app = FastAPI(title="ANDORA Backend API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health_router)
app.include_router(livekit_router)
app.include_router(conversations_router)
app.mount("/tester", StaticFiles(directory="frontend", html=True), name="tester")
app.include_router(documents_router)
