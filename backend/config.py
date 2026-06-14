import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "tutor.db"

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000")

CHUNK_SIZE = 600
CHUNK_OVERLAP = 80
