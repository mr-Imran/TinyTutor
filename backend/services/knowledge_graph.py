"""One concept map across every document, with prerequisite links and learning paths.

Concepts come from each document's summary concept map. The same concept from different documents
is merged by name, and by meaning when embeddings are available. Links:
- related: copied from the document concept maps.
- prereq:  "understand A before B", labelled by the AI once per change in the concept set.
The student can delete, flip or add links; deleted links are remembered so a rebuild keeps them gone.
"""
import hashlib
import json
import re
from collections import defaultdict, deque

import numpy as np

from database import get_db
from services import llm
from services.settings_store import get_setting, set_setting

MERGE_SIMILARITY = 0.9
MAX_AI_CONCEPTS = 80
MASTERED = 80.0
WEAK = 50.0

PREREQ_SYSTEM = (
    "You order study concepts. Return ONLY valid JSON, no markdown: "
    '{"prerequisites":[{"before":"concept name","after":"concept name"}]}. '
    "List a pair only when a student truly needs to understand 'before' to learn 'after'. "
    "Use the concept names exactly as given. Never create cycles. Prefer few, certain links."
)


class GraphError(Exception):
    pass


def concept_key(term: str) -> str:
    key = re.sub(r"[^\w\s-]", "", term.lower())
    key = re.sub(r"[\s_-]+", " ", key).strip()
    if len(key) > 4 and key.endswith("s") and not key.endswith(("ss", "us", "is")):
        key = key[:-1]
    return key


def _collect(user_id: int) -> dict[str, dict]:
    with get_db() as conn:
        docs = conn.execute(
            "SELECT id, title, topic, concepts_json FROM documents WHERE user_id = ? AND concepts_json IS NOT NULL",
            (user_id,),
        ).fetchall()
    concepts: dict[str, dict] = {}
    for d in docs:
        for c in json.loads(d["concepts_json"] or "[]"):
            key = concept_key(c.get("term", ""))
            if not key:
                continue
            item = concepts.setdefault(key, {
                "key": key, "name": c["term"].strip(), "definition": "", "topic": d["topic"],
                "document_ids": [], "related": set(),
            })
            if len(c.get("definition", "")) > len(item["definition"]):
                item["definition"] = c["definition"].strip()
            if d["id"] not in item["document_ids"]:
                item["document_ids"].append(d["id"])
            item["related"].update(concept_key(r) for r in c.get("related") or [])
    return concepts


async def _merge_by_meaning(concepts: dict[str, dict]) -> dict[str, str]:
    """Map each key to its canonical key, joining concepts whose name+definition mean the same."""
    from services.embeddings import EmbeddingError, _normalize, embed_texts

    keys = list(concepts)
    canonical = {k: k for k in keys}
    if len(keys) < 2:
        return canonical
    try:
        vectors = _normalize(await embed_texts([f"{concepts[k]['name']}: {concepts[k]['definition']}" for k in keys]))
    except EmbeddingError:
        return canonical
    sims = vectors @ vectors.T
    parent = list(range(len(keys)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in zip(*np.where(np.triu(sims, k=1) >= MERGE_SIMILARITY)):
        a, b = find(int(i)), find(int(j))
        if a != b:
            # Keep the concept that appears in more documents as the canonical one.
            if len(concepts[keys[a]]["document_ids"]) < len(concepts[keys[b]]["document_ids"]):
                a, b = b, a
            parent[b] = a
    return {k: keys[find(i)] for i, k in enumerate(keys)}


def _apply_merge(concepts: dict[str, dict], canonical: dict[str, str]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for key, c in concepts.items():
        target = canonical[key]
        m = merged.setdefault(target, {**concepts[target], "document_ids": [], "related": set()})
        m["document_ids"] += [d for d in c["document_ids"] if d not in m["document_ids"]]
        m["related"] |= {canonical.get(r, r) for r in c["related"]}
        if len(c["definition"]) > len(m["definition"]):
            m["definition"] = c["definition"]
    for m in merged.values():
        m["related"] = {r for r in m["related"] if r in merged and r != m["key"]}
    return merged


def _store(user_id: int, concepts: dict[str, dict]):
    with get_db() as conn:
        conn.execute("DELETE FROM concepts WHERE user_id = ?", (user_id,))
        conn.executemany(
            """INSERT INTO concepts (user_id, key, name, definition, topic, document_ids_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(user_id, c["key"], c["name"], c["definition"], c["topic"], json.dumps(c["document_ids"]))
             for c in concepts.values()],
        )
        # Links from document concept maps; INSERT OR IGNORE keeps links the student removed removed.
        pairs = {tuple(sorted((c["key"], r))) for c in concepts.values() for r in c["related"]}
        conn.executemany(
            """INSERT OR IGNORE INTO concept_links (user_id, source_key, target_key, kind, origin)
               VALUES (?, ?, ?, 'related', 'doc')""",
            [(user_id, a, b) for a, b in pairs],
        )


async def _label_prerequisites(user_id: int, concepts: dict[str, dict]) -> int:
    chosen = sorted(concepts.values(), key=lambda c: -len(c["document_ids"]))[:MAX_AI_CONCEPTS]
    listing = "\n".join(f"- {c['name']}: {c['definition'][:160]}" for c in chosen)
    from services.ai import _extract_json

    raw = await llm.complete([{"role": "user", "content": f"Concepts:\n{listing}"}], system=PREREQ_SYSTEM,
                             json_mode=True, temperature=0)
    data = json.loads(_extract_json(raw))
    pairs = []
    for p in (data.get("prerequisites") if isinstance(data, dict) else None) or []:
        if not isinstance(p, dict):
            continue
        a, b = concept_key(str(p.get("before", ""))), concept_key(str(p.get("after", "")))
        if a in concepts and b in concepts and a != b:
            pairs.append((a, b))
    with get_db() as conn:
        conn.execute(
            "DELETE FROM concept_links WHERE user_id = ? AND kind = 'prereq' AND origin = 'ai' AND removed = 0",
            (user_id,),
        )
        conn.executemany(
            """INSERT OR IGNORE INTO concept_links (user_id, source_key, target_key, kind, origin)
               VALUES (?, ?, ?, 'prereq', 'ai')""",
            [(user_id, a, b) for a, b in pairs],
        )
    return len(pairs)


async def rebuild(user_id: int, use_ai: bool = True, force_ai: bool = False) -> dict:
    concepts = _collect(user_id)
    concepts = _apply_merge(concepts, await _merge_by_meaning(concepts))
    _store(user_id, concepts)
    warning = None
    digest = hashlib.sha1(json.dumps(sorted(concepts)).encode()).hexdigest()
    hash_key = f"kg_prereq_hash_{user_id}"
    if use_ai and len(concepts) >= 2 and (force_ai or get_setting(hash_key) != digest):
        try:
            await _label_prerequisites(user_id, concepts)
            set_setting(hash_key, digest)
        except (llm.LLMError, json.JSONDecodeError, TypeError, AttributeError) as e:
            warning = f"Prerequisites were not updated: {e}"
    return {**get_graph(user_id), "warning": warning}


def _mastery(user_id: int) -> dict[str, float]:
    from services.mastery import refresh_mastery

    refresh_mastery(user_id)
    with get_db() as conn:
        return {r["topic"]: r["mastery_percentage"] for r in conn.execute(
            "SELECT topic, mastery_percentage FROM topic_scores WHERE user_id = ?", (user_id,)
        )}


def _level(mastery: float | None) -> str:
    if mastery is None:
        return "unknown"
    return "mastered" if mastery >= MASTERED else "learning" if mastery >= WEAK else "weak"


def get_graph(user_id: int) -> dict:
    mastery = _mastery(user_id)
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM concepts WHERE user_id = ? ORDER BY name", (user_id,)).fetchall()
        titles = {r["id"]: r["title"] for r in conn.execute(
            "SELECT id, title FROM documents WHERE user_id = ?", (user_id,)
        )}
        links = conn.execute(
            "SELECT id, source_key, target_key, kind, origin FROM concept_links WHERE user_id = ? AND removed = 0",
            (user_id,),
        ).fetchall()
    nodes = []
    for r in rows:
        m = mastery.get(r["topic"])
        nodes.append({
            "key": r["key"], "name": r["name"], "definition": r["definition"], "topic": r["topic"],
            "documents": [{"id": d, "title": titles[d]} for d in json.loads(r["document_ids_json"]) if d in titles],
            "mastery": m, "level": _level(m),
        })
    known = {n["key"] for n in nodes}
    edges = [
        {"id": link["id"], "source": link["source_key"], "target": link["target_key"], "kind": link["kind"],
         "origin": link["origin"]}
        for link in links if link["source_key"] in known and link["target_key"] in known
    ]
    return {"nodes": nodes, "edges": edges}


def learning_path(user_id: int, key: str) -> dict:
    graph = get_graph(user_id)
    nodes = {n["key"]: n for n in graph["nodes"]}
    if key not in nodes:
        raise GraphError("Concept not found")
    before = defaultdict(set)  # concept -> its direct prerequisites
    for e in graph["edges"]:
        if e["kind"] == "prereq":
            before[e["target"]].add(e["source"])

    needed, stack = set(), [key]
    while stack:
        k = stack.pop()
        if k in needed:
            continue
        needed.add(k)
        stack.extend(before[k])

    # Kahn's algorithm on the prerequisite subgraph; a cycle (if the AI or student made one) is
    # broken by taking the remaining concepts in name order.
    indegree = {k: len(before[k] & needed) for k in needed}
    queue = deque(sorted((k for k, d in indegree.items() if d == 0), key=lambda k: nodes[k]["name"]))
    order = []
    while queue:
        k = queue.popleft()
        order.append(k)
        for other in sorted(needed, key=lambda k: nodes[k]["name"]):
            if k in before[other] and other not in order and other not in queue:
                indegree[other] -= 1
                if indegree[other] == 0:
                    queue.append(other)
    order += sorted((k for k in needed if k not in order), key=lambda k: nodes[k]["name"])
    if key in order:  # the target always comes last
        order.remove(key)
    order.append(key)

    steps = [nodes[k] for k in order if k == key or nodes[k]["level"] != "mastered"]
    skipped = [nodes[k]["name"] for k in order if k != key and nodes[k]["level"] == "mastered"]
    return {"target": nodes[key], "steps": steps, "skipped": skipped}


def _link(user_id: int, link_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM concept_links WHERE id = ? AND user_id = ?", (link_id, user_id)
        ).fetchone()
    if not row:
        raise GraphError("Link not found")
    return row


def remove_link(user_id: int, link_id: int):
    _link(user_id, link_id)
    with get_db() as conn:
        conn.execute("UPDATE concept_links SET removed = 1 WHERE id = ?", (link_id,))


def add_link(user_id: int, source: str, target: str, kind: str = "prereq"):
    if kind not in ("prereq", "related"):
        raise GraphError("Unknown link kind")
    if source == target:
        raise GraphError("A concept cannot link to itself")
    with get_db() as conn:
        found = conn.execute(
            "SELECT COUNT(*) c FROM concepts WHERE user_id = ? AND key IN (?, ?)", (user_id, source, target)
        ).fetchone()["c"]
        if found != 2:
            raise GraphError("Concept not found")
        conn.execute(
            """INSERT INTO concept_links (user_id, source_key, target_key, kind, origin, removed)
               VALUES (?, ?, ?, ?, 'user', 0)
               ON CONFLICT(user_id, source_key, target_key, kind) DO UPDATE SET removed = 0, origin = 'user'""",
            (user_id, source, target, kind),
        )


def flip_link(user_id: int, link_id: int):
    row = _link(user_id, link_id)
    remove_link(user_id, link_id)
    add_link(user_id, row["target_key"], row["source_key"], row["kind"])
