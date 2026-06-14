from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from database import init_db
from routers import chat, dashboard, database_viewer, documents, exam_tools, quiz, study
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
)

app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(quiz.router)
app.include_router(dashboard.router)
app.include_router(database_viewer.router)
app.include_router(study.router)
app.include_router(exam_tools.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
