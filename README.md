# TinyTutor — AI Exam Monitor & Study Tutor

A simple, local-first AI study tutor. Upload PDFs/PPTX, chat with your materials, take AI-generated quizzes, and track weak topics — optimized for low-end hardware.

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python, FastAPI, SQLite, Ollama, APScheduler |
| Frontend | Next.js 15, TypeScript, Tailwind, Framer Motion, shadcn-style UI, Recharts |
| AI | `qwen2.5:0.5b` via Ollama (configurable) |

## Project Structure

```
TinyTutor/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── database.py          # SQLite schema
│   ├── config.py
│   ├── routers/             # API routes
│   └── services/            # Documents, search, AI, quiz, scheduler
├── frontend/                # Next.js app
└── README.md
```

## Prerequisites

1. **Python 3.10–3.14** (3.14 works; 3.10–3.12 recommended for smoothest installs)
2. **Node.js 18+**
3. **Ollama** — [https://ollama.com](https://ollama.com)

```bash
ollama pull qwen2.5:0.5b
# or: ollama pull gemma3:270m  (then edit backend/config.py)
```

## Quick Start

### Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open **http://localhost:3000**

## Features

- **Upload** — PDF (PyMuPDF) and PPTX (python-pptx) → chunked into SQLite
- **Search** — keyword matching (no vector DB)
- **AI Tutor** — chat grounded in your uploaded chunks
- **Quiz Center** — MCQ, True/False, Short Answer; easy/medium/hard
- **Exam simulation** — 5-question practice exams
- **Dashboard** — streak, readiness, weak/strong topics
- **Analytics** — Recharts mastery & activity charts
- **Local DB viewer** — browse all SQLite tables; add/edit/delete knowledge chunks for extra AI context
- **Scheduler** — every 30 min, one question on a weak topic (notification)

## API Overview

| Endpoint | Description |
|----------|-------------|
| `POST /api/documents/upload` | Upload PDF/PPTX |
| `GET /api/documents` | List documents |
| `POST /api/chat` | AI tutor chat |
| `POST /api/quiz/generate` | Generate question |
| `POST /api/quiz/submit` | Submit & grade answer |
| `POST /api/quiz/exam` | Simulate exam |
| `GET /api/dashboard` | Dashboard stats |
| `GET /api/dashboard/analytics` | Charts data |
| `GET /api/db/overview` | Table list + row counts |
| `GET /api/db/tables/{table}` | Browse rows (paginated) |
| `POST /api/db/context` | Add manual knowledge chunk |
| `PUT /api/db/chunks/{id}` | Edit chunk |
| `DELETE /api/db/chunks/{id}` | Delete chunk |

## Notes

- Default user id is `1` (single-student mode — simple by design).
- AI runs only on request; scheduler fires every 30 minutes, not continuously.
- Max upload size: 25MB per file.
