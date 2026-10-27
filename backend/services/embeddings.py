"""Text embeddings for semantic search, stored as float32 blobs in SQLite.

Anthropic has no embeddings API, so with Claude (or Ollama) as the chat provider the
default is a local Ollama embedding model. Search silently falls back to keyword-only
when no embedding model is reachable.
"""
import logging

import httpx
import numpy as np

from database import get_db
from services import llm
from services.settings_store import get_setting

logger = logging.getLogger(__name__)

EMBED_PROVIDERS = ("auto", "ollama", "openai", "gemini", "off")
DEFAULT_EMBED_MODELS = {
    "ollama": "nomic-embed-text",
    "openai": "text-embedding-3-small",
    "gemini": "gemini-embedding-001",
}
BATCH_SIZE = 32
MAX_CHARS = 2000


class EmbeddingError(Exception):
    pass


def get_embed_config() -> dict:
    """Resolve which provider/model embeds text. provider is None when embeddings are off."""
    choice = get_setting("embed_provider", "auto")
    if choice == "off":
        return {"provider": None, "model": None}
    if choice not in DEFAULT_EMBED_MODELS:  # "auto": follow the chat provider when it can embed
        chat = llm.get_llm_config()["provider"]
        choice = chat if chat in ("openai", "gemini") else "ollama"
    base = llm.get_llm_config(choice)
    return {
        **base,
        "provider": choice,
        "model": get_setting(f"embed_model_{choice}", DEFAULT_EMBED_MODELS[choice]),
    }


async def embed_texts(texts: list[str], cfg: dict | None = None) -> list[list[float]]:
    cfg = cfg or get_embed_config()
    if not cfg["provider"]:
        raise EmbeddingError("Embeddings are turned off.")
    texts = [t[:MAX_CHARS] for t in texts]
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            if cfg["provider"] == "ollama":
                resp = await client.post(f"{cfg['base_url']}/api/embed", json={"model": cfg["model"], "input": texts})
                resp.raise_for_status()
                return resp.json()["embeddings"]
            if cfg["provider"] == "openai":
                resp = await client.post(
                    f"{cfg['base_url']}/embeddings",
                    json={"model": cfg["model"], "input": texts},
                    headers=llm._openai_headers(cfg),
                )
                resp.raise_for_status()
                return [d["embedding"] for d in sorted(resp.json()["data"], key=lambda d: d["index"])]
            if cfg["provider"] == "gemini":
                model = f"models/{cfg['model']}"
                resp = await client.post(
                    f"{llm.GEMINI_BASE}/{model}:batchEmbedContents",
                    json={"requests": [{"model": model, "content": {"parts": [{"text": t}]}} for t in texts]},
                    headers=llm._gemini_headers(cfg),
                )
                resp.raise_for_status()
                return [e["values"] for e in resp.json()["embeddings"]]
    except (httpx.HTTPError, KeyError, ValueError, llm.LLMError) as e:
        raise EmbeddingError(str(e)) from e
    raise EmbeddingError(f"Unknown embedding provider {cfg['provider']}")


def _normalize(vectors: list[list[float]]) -> np.ndarray:
    arr = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.where(norms == 0, 1, norms)


async def index_chunks(user_id: int, document_id: int | None = None, limit: int | None = None) -> int:
    """Embed chunks that have no vector for the current model. Returns how many were embedded."""
    cfg = get_embed_config()
    if not cfg["provider"]:
        return 0
    sql = """SELECT c.id, c.title, c.content FROM knowledge_chunks c
             LEFT JOIN chunk_embeddings e ON e.chunk_id = c.id AND e.model = ?
             WHERE c.user_id = ? AND e.chunk_id IS NULL"""
    params: list = [cfg["model"], user_id]
    if document_id is not None:
        sql += " AND c.document_id = ?"
        params.append(document_id)
    sql += " ORDER BY c.id"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_db() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

    done = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        vectors = _normalize(await embed_texts([f"{r['title']}\n{r['content']}" for r in batch], cfg))
        with get_db() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO chunk_embeddings (chunk_id, model, dim, vector) VALUES (?, ?, ?, ?)",
                [(r["id"], cfg["model"], vectors.shape[1], v.tobytes()) for r, v in zip(batch, vectors)],
            )
        done += len(batch)
    return done


async def index_document_quietly(user_id: int, document_id: int):
    """Background task after upload: failures only mean keyword-only search for now."""
    try:
        await index_chunks(user_id, document_id)
    except EmbeddingError as e:
        logger.info("Embedding skipped for document %s: %s", document_id, e)


async def semantic_search(user_id: int, query: str, topic: str | None = None, limit: int = 10) -> list[tuple[int, float]]:
    """Returns [(chunk_id, cosine_similarity)] best first. Empty when nothing is indexed."""
    cfg = get_embed_config()
    if not cfg["provider"] or not query.strip():
        return []
    sql = """SELECT e.chunk_id, e.vector FROM chunk_embeddings e
             JOIN knowledge_chunks c ON c.id = e.chunk_id
             WHERE c.user_id = ? AND e.model = ?"""
    params: list = [user_id, cfg["model"]]
    if topic:
        sql += " AND LOWER(c.topic) LIKE ?"
        params.append(f"%{topic.lower()}%")
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return []
    query_vec = _normalize(await embed_texts([query], cfg))[0]
    matrix = np.stack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows])
    if matrix.shape[1] != query_vec.shape[0]:
        return []
    scores = matrix @ query_vec
    top = np.argsort(-scores)[:limit]
    return [(rows[i]["chunk_id"], float(scores[i])) for i in top]


def index_status(user_id: int) -> dict:
    cfg = get_embed_config()
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM knowledge_chunks WHERE user_id = ?", (user_id,)).fetchone()["c"]
        indexed = conn.execute(
            """SELECT COUNT(*) c FROM chunk_embeddings e JOIN knowledge_chunks k ON k.id = e.chunk_id
               WHERE k.user_id = ? AND e.model = ?""",
            (user_id, cfg["model"]),
        ).fetchone()["c"] if cfg["provider"] else 0
    return {"provider": cfg["provider"], "model": cfg["model"], "indexed": indexed, "total": total}
