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
    grading,
    knowledge,
    math,
    misconceptions,
    mock_exams,
    notes,
    plan,
    progress,
    quiz,
    search,
    settings,
    study,
    usage,
)
from services.scheduler import start_scheduler
from services.transcription import mark_interrupted
from services.usage import FeatureMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    mark_interrupted()
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
app.add_middleware(FeatureMiddleware)

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
app.include_router(grading.router)
app.include_router(misconceptions.router)
app.include_router(knowledge.router)
app.include_router(notes.router)
app.include_router(usage.router)
app.include_router(math.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
