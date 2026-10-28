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

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'tutor',
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
);

CREATE TABLE IF NOT EXISTS flashcards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    document_id INTEGER,
    topic TEXT NOT NULL,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    ease REAL NOT NULL DEFAULT 2.5,
    interval_days INTEGER NOT NULL DEFAULT 0,
    repetitions INTEGER NOT NULL DEFAULT 0,
    due_at TEXT NOT NULL,
    last_reviewed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS mastery_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    is_correct INTEGER NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    source TEXT NOT NULL DEFAULT 'quiz',
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS mock_exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topics_json TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_progress',
    started_at TEXT NOT NULL,
    deadline_at TEXT NOT NULL,
    submitted_at TEXT,
    score INTEGER,
    total INTEGER NOT NULL,
    late INTEGER DEFAULT 0,
    report_json TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS mock_exam_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    topic TEXT NOT NULL,
    question_type TEXT NOT NULL,
    question TEXT NOT NULL,
    options_json TEXT,
    correct_answer TEXT NOT NULL,
    explanation TEXT,
    user_answer TEXT,
    is_correct INTEGER,
    feedback TEXT,
    FOREIGN KEY (exam_id) REFERENCES mock_exams(id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON knowledge_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_flashcards_due ON flashcards(user_id, due_at);
CREATE INDEX IF NOT EXISTS idx_mastery_events_topic ON mastery_events(user_id, topic);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id INTEGER PRIMARY KEY,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL,
    FOREIGN KEY (chunk_id) REFERENCES knowledge_chunks(id)
);

CREATE TRIGGER IF NOT EXISTS chunks_embedding_delete AFTER DELETE ON knowledge_chunks BEGIN
    DELETE FROM chunk_embeddings WHERE chunk_id = old.id;
END;

-- Edited text makes the stored embedding stale.
CREATE TRIGGER IF NOT EXISTS chunks_embedding_update AFTER UPDATE OF content ON knowledge_chunks BEGIN
    DELETE FROM chunk_embeddings WHERE chunk_id = old.id;
END;

CREATE TABLE IF NOT EXISTS daily_plans (
    user_id INTEGER NOT NULL,
    plan_date TEXT NOT NULL,
    tasks_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, plan_date),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS badges (
    user_id INTEGER NOT NULL,
    badge_id TEXT NOT NULL,
    earned_at TEXT NOT NULL,
    seen INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, badge_id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    feature TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_created ON llm_usage(created_at);

CREATE TABLE IF NOT EXISTS graded_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    topic TEXT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    rubric_json TEXT,
    result_json TEXT NOT NULL,
    score REAL NOT NULL,
    max_score REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS misconceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    correction TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    streak INTEGER NOT NULL DEFAULT 0,
    drill_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Which wrong answers were looked at by an analysis, and the misconception they fed (if any).
CREATE TABLE IF NOT EXISTS misconception_attempts (
    attempt_id INTEGER PRIMARY KEY,
    misconception_id INTEGER,
    FOREIGN KEY (attempt_id) REFERENCES quiz_attempts(id)
);

CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    name TEXT NOT NULL,
    definition TEXT,
    topic TEXT,
    document_ids_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE(user_id, key),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- kind 'prereq': source must be understood before target. origin: doc | ai | user.
-- removed = 1 keeps a link the student deleted, so a rebuild does not bring it back.
CREATE TABLE IF NOT EXISTS concept_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    source_key TEXT NOT NULL,
    target_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    origin TEXT NOT NULL,
    removed INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, source_key, target_key, kind),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    title, topic, content,
    content='knowledge_chunks', content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS chunks_fts_insert AFTER INSERT ON knowledge_chunks BEGIN
    INSERT INTO chunks_fts(rowid, title, topic, content)
    VALUES (new.id, new.title, new.topic, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_delete AFTER DELETE ON knowledge_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, title, topic, content)
    VALUES ('delete', old.id, old.title, old.topic, old.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_update AFTER UPDATE ON knowledge_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, title, topic, content)
    VALUES ('delete', old.id, old.title, old.topic, old.content);
    INSERT INTO chunks_fts(rowid, title, topic, content)
    VALUES (new.id, new.title, new.topic, new.content);
END;
"""

# table -> {column: definition} added to databases created before the column existed
COLUMN_MIGRATIONS = {
    "scheduled_questions": {"notification_type": "TEXT DEFAULT 'quiz'"},
    "documents": {
        "stored_name": "TEXT",
        "summary": "TEXT",
        "concepts_json": "TEXT",
        "summary_status": "TEXT",
        "source_url": "TEXT",
        "body": "TEXT",  # markdown of notes written in the app (file_type 'note')
        "updated_at": "TEXT",
        "media_status": "TEXT",  # audio/video transcription: pending | running | done | failed | cancelled
        "media_progress": "REAL",
        "media_error": "TEXT",
        "duration_seconds": "REAL",
    },
    "knowledge_chunks": {"page_number": "INTEGER", "start_seconds": "INTEGER"},
    "flashcards": {
        "annotation_id": "INTEGER",
        "card_type": "TEXT NOT NULL DEFAULT 'basic'",  # basic | cloze | occlusion
        "note_id": "TEXT",  # sibling cards made from one cloze text or one occlusion image
        "cloze_index": "INTEGER",
        "image_name": "TEXT",
        "masks_json": "TEXT",
    },
    "chat_messages": {"cards_json": "TEXT", "grounding_json": "TEXT"},
}


def _migrate(conn):
    for table, columns in COLUMN_MIGRATIONS.items():
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    has_fts = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chunks_fts'"
    ).fetchone()
    if not has_fts:
        conn.executescript(FTS_SCHEMA)
        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")

    # One-time: seed recency-weighted mastery from quiz history recorded before it existed.
    if not conn.execute("SELECT 1 FROM app_settings WHERE key = 'mastery_backfilled'").fetchone():
        conn.execute(
            """INSERT INTO mastery_events (user_id, topic, is_correct, weight, source, created_at)
               SELECT user_id, COALESCE(topic, 'General'), is_correct,
                      CASE difficulty WHEN 'easy' THEN 0.8 WHEN 'hard' THEN 1.25 ELSE 1.0 END,
                      'quiz', created_at
               FROM quiz_attempts WHERE is_correct IS NOT NULL"""
        )
        conn.execute("INSERT INTO app_settings (key, value) VALUES ('mastery_backfilled', '1')")


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
