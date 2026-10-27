from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from database import init_db
from routers import (
    chat,
    dashboard,
    data,
    database_viewer,
    documents,
    exam_tools,
    flashcards,
    mock_exams,
    plan,
    progress,
    quiz,
    search,
    settings,
    study,
)
from services.scheduler import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield


app = FastAPI(title="TinyTutor API", lifespan=lifespan)

origins = [o.strip() for o in CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-Id", "X-Sources"],
)

app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(quiz.router)
app.include_router(dashboard.router)
app.include_router(database_viewer.router)
app.include_router(study.router)
app.include_router(exam_tools.router)
app.include_router(settings.router)
app.include_router(search.router)
app.include_router(flashcards.router)
app.include_router(mock_exams.router)
app.include_router(plan.router)
app.include_router(progress.router)
app.include_router(data.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
