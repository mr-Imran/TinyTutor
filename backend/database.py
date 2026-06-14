import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT,
    study_streak INTEGER DEFAULT 0,
    last_study_date TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    title TEXT,
    topic TEXT,
    page_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    title TEXT,
    topic TEXT,
    content TEXT NOT NULL,
    source TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic TEXT,
    question_type TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    question TEXT NOT NULL,
    options_json TEXT,
    correct_answer TEXT NOT NULL,
    user_answer TEXT,
    is_correct INTEGER,
    score REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS topic_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    correct_answers INTEGER DEFAULT 0,
    wrong_answers INTEGER DEFAULT 0,
    mastery_percentage REAL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, topic),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS scheduled_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    question TEXT NOT NULL,
    question_type TEXT NOT NULL,
    options_json TEXT,
    correct_answer TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,
    notification_type TEXT DEFAULT 'quiz',
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS exam_plan (
    user_id INTEGER PRIMARY KEY,
    exam_start TEXT NOT NULL,
    exam_end TEXT NOT NULL,
    expected_cgpa REAL NOT NULL DEFAULT 8.0,
    current_cgpa REAL DEFAULT 6.0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS study_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    minutes INTEGER NOT NULL,
    topic TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS document_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    page_number INTEGER,
    marker_type TEXT NOT NULL,
    color TEXT,
    selected_text TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (document_id) REFERENCES documents(id)
);
"""


def _migrate(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(scheduled_questions)").fetchall()}
    if "notification_type" not in cols:
        conn.execute(
            "ALTER TABLE scheduled_questions ADD COLUMN notification_type TEXT DEFAULT 'quiz'"
        )


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "uploads").mkdir(exist_ok=True)
    with get_db() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        row = conn.execute("SELECT id FROM users WHERE id = 1").fetchone()
        if not row:
            now = datetime.utcnow().isoformat()
            conn.execute(
                "INSERT INTO users (id, username, display_name, created_at) VALUES (1, 'student', 'Student', ?)",
                (now,),
            )


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row) -> dict | None:
    if row is None:
        return None
    return dict(row)
