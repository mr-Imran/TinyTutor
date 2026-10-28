"""Manage local Ollama models from the app: hardware check, suggestions, download, delete.

Sizes in the catalog are approximate download sizes; a model needs roughly its size plus 1-2 GB
of free memory (RAM, or VRAM on a GPU) to run comfortably.
"""
import json
import shutil
import subprocess
from typing import AsyncIterator

import httpx

from services import llm

# name, approx download GB, purpose, what it is good for
CATALOG = [
    ("qwen2.5:0.5b", 0.4, "chat", "Tiny and fast; fine for flashcards, weak at long answers"),
    ("llama3.2:3b", 2.0, "chat", "Good all-round tutor on modest laptops; supports tools"),
    ("qwen2.5:3b", 1.9, "chat", "Good all-round tutor on modest laptops; supports tools"),
    ("qwen2.5:7b", 4.7, "chat", "Noticeably better explanations and grading; supports tools"),
    ("llama3.1:8b", 4.9, "chat", "Strong general tutor; supports tools"),
    ("qwen2.5:14b", 9.0, "chat", "High quality; needs a strong GPU or 16GB+ RAM"),
    ("qwen2.5vl:3b", 3.2, "vision", "Reads photos of notes and scanned pages"),
    ("qwen2.5vl:7b", 6.0, "vision", "Better handwriting and diagram reading"),
    ("gemma3:4b", 3.3, "vision", "Vision and chat in one model"),
    ("nomic-embed-text", 0.3, "embedding", "Search by meaning (recommended)"),
    ("mxbai-embed-large", 0.7, "embedding", "Search by meaning, slightly stronger, bigger"),
]
HEADROOM_GB = 1.5


def _gpu() -> dict | None:
    """NVIDIA GPU name and memory via nvidia-smi; None when there is no NVIDIA GPU."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip().splitlines()
    except (subprocess.SubprocessError, OSError):
        return None
    if not out:
        return None
    name, mem = [p.strip() for p in out[0].split(",")[:2]]
    try:
        return {"name": name, "memory_gb": round(float(mem) / 1024, 1)}
    except ValueError:
        return {"name": name, "memory_gb": None}


def system_info() -> dict:
    import os

    import psutil

    mem = psutil.virtual_memory()
    gpu = _gpu()
    budget = max(gpu["memory_gb"] or 0, 0) if gpu else round(mem.available / 1024**3, 1)
    return {
        "ram_total_gb": round(mem.total / 1024**3, 1),
        "ram_available_gb": round(mem.available / 1024**3, 1),
        "cpu_count": os.cpu_count(),
        "gpu": gpu,
        # Memory the largest model can use: VRAM when a GPU is present, else free RAM.
        "model_budget_gb": budget,
    }


def recommendations(info: dict, installed: set[str]) -> list[dict]:
    budget = info["model_budget_gb"] or 0
    out = []
    for name, size, purpose, note in CATALOG:
        fits = size + HEADROOM_GB <= budget
        out.append({"name": name, "size_gb": size, "purpose": purpose, "note": note, "fits": fits,
                    "installed": name in installed or f"{name}:latest" in installed})
    # Best chat pick: the largest chat model that fits.
    chat = [r for r in out if r["purpose"] == "chat" and r["fits"]]
    best = max(chat, key=lambda r: r["size_gb"])["name"] if chat else "qwen2.5:0.5b"
    for r in out:
        r["recommended"] = r["name"] in (best, "nomic-embed-text") or (
            r["purpose"] == "vision" and r["fits"] and r["name"] == _best_vision(out))
    return out


def _best_vision(rows: list[dict]) -> str | None:
    fits = [r for r in rows if r["purpose"] == "vision" and r["fits"]]
    return max(fits, key=lambda r: r["size_gb"])["name"] if fits else None


def _base() -> str:
    return llm.get_llm_config("ollama")["base_url"]


async def installed_models() -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{_base()}/api/tags")
        resp.raise_for_status()
        tags = resp.json().get("models", [])
        try:
            running = {m["name"] for m in (await client.get(f"{_base()}/api/ps")).json().get("models", [])}
        except (httpx.HTTPError, ValueError):
            running = set()
    return [
        {"name": m["name"], "size_gb": round(m.get("size", 0) / 1024**3, 2),
         "modified_at": m.get("modified_at"), "family": (m.get("details") or {}).get("family"),
         "parameters": (m.get("details") or {}).get("parameter_size"), "running": m["name"] in running}
        for m in tags
    ]


async def pull(name: str) -> AsyncIterator[dict]:
    """Yields {"status", "completed", "total", "percent"} while Ollama downloads, then {"status": "success"}."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=None)) as client:
        async with client.stream("POST", f"{_base()}/api/pull", json={"model": name, "stream": True}) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                yield {"status": "error", "error": body.decode(errors="replace")[:300] or resp.reason_phrase}
                return
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "error" in data:
                    yield {"status": "error", "error": data["error"]}
                    return
                total, done = data.get("total"), data.get("completed")
                yield {"status": data.get("status", ""), "completed": done, "total": total,
                       "percent": round(done / total * 100, 1) if total and done else None}


async def delete(name: str):
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request("DELETE", f"{_base()}/api/delete", json={"model": name, "name": name})
        resp.raise_for_status()
