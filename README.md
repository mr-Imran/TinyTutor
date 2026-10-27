# TinyTutor: The Ultimate Local-First AI Study Tutor & Exam Monitor

**TinyTutor** is a powerful, local-first **AI study tutor** and **exam monitor** designed to help students, developers, and lifelong learners master any subject. Upload course materials (PDF, DOCX, PPTX, TXT, Markdown), chat with your documents with page-level citations, review AI-generated flashcards with spaced repetition, take timed mock exams, and track your learning progress. Run it fully offline with **Ollama**, or plug in **Anthropic Claude**, **Google Gemini**, or any **OpenAI-compatible** API.

## 🚀 Key Features

*   **📚 Document Chat with Citations (RAG)**: Upload PDF, DOCX, PPTX, TXT and Markdown files. Answers cite the exact note they came from (`[1]`, `[2]`) and link straight to the PDF page.
*   **💬 Saved Conversations**: Tutor and mentor chats are saved as sessions. Follow-up questions keep their context, and past chats are one click away.
*   **🔎 Full-Text Search**: SQLite FTS5 with BM25 ranking powers fast, relevant search across all your materials, with highlighted snippets.
*   **📝 Auto Summaries & Concept Maps**: Every upload gets an AI summary and a map of key terms and how they connect.
*   **🃏 Spaced-Repetition Flashcards**: Generate flashcards from any topic or document and review them on an SM-2 schedule. Reviews feed your mastery scores.
*   **⏱️ Timed Mock Exams**: Mixed multiple-choice, true/false and short-answer questions against a countdown. No feedback until you submit, then a per-topic report.
*   **🧠 AI-Generated Quizzes**: Multiple choice, true/false, short-answer and open-ended questions at easy, medium or hard difficulty.
*   **📈 Recency-Weighted Mastery**: Recent and harder answers count more. Topics you have not practised slowly drift back toward 50%, and Analytics charts your mastery week by week.
*   **🎓 Exam Hub**: CGPA calculator, previous-question and slide analysis, midterm/final predictor, viva simulator and a PDF reader with highlights.
*   **⏰ Automated Study Scheduler**: Every 30 minutes, a practice question on your weakest topic (or a study reminder during your exam window).
*   **🔌 Choose Your AI**: Ollama (default, local and private), Anthropic Claude, Google Gemini, or OpenAI-compatible endpoints (OpenAI, Groq, OpenRouter, LM Studio, vLLM). Switch in Settings without restarting.
*   **🗄️ Built-in Database Viewer**: Browse tables and add, edit or delete knowledge chunks from the UI.

## 🛠️ Technology Stack

*   **Backend**: Python, [FastAPI](https://fastapi.tiangolo.com/), SQLite (FTS5), APScheduler, PyMuPDF, python-pptx, python-docx, the official `anthropic` SDK, httpx.
*   **Frontend**: [Next.js 15](https://nextjs.org/), React, TypeScript, Tailwind CSS, Framer Motion, shadcn/ui components, Recharts.
*   **AI Engine**: One provider interface (`backend/services/llm.py`) over Ollama, Anthropic, Gemini and OpenAI-compatible APIs. No vector database required.

## 🎯 Who is TinyTutor For?

*   **Students**: Turn lecture slides and textbook PDFs into interactive tutors, flashcards and mock exams.
*   **Self-Learners**: Generate quizzes and flashcards to reinforce learning on any topic.
*   **Developers**: A starter template for building multi-provider AI apps with FastAPI and Next.js.

## ⚙️ Prerequisites

1.  **Python 3.10–3.14** (3.10–3.12 recommended for the smoothest installation)
2.  **Node.js 18+**
3.  **One AI provider**:
    *   **Ollama** (default, fully local) — download at [ollama.com](https://ollama.com), then `ollama pull qwen2.5:0.5b`
    *   or an API key for **Anthropic**, **Google Gemini**, or an **OpenAI-compatible** service
4.  *(Optional)* **Tesseract OCR** for scanned PDFs — PyMuPDF uses it automatically when installed and `TESSDATA_PREFIX` is set.

## 💻 Installation & Quick Start

### 1. Start the FastAPI Backend

```bash
cd backend
python -m venv venv

# Activate Virtual Environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
*The backend API will be available at `http://localhost:8000`*

### 2. Start the Next.js Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```
*Open the TinyTutor dashboard at **`http://localhost:3000`***

### 3. Pick your AI model

Open **Settings**. Choose a provider, paste an API key if it needs one, and pick a model from the list. The dot at the bottom of the sidebar shows whether the AI is reachable.

You can also configure providers with environment variables. Values saved in Settings take precedence.

| Variable | Purpose |
|----------|---------|
| `LLM_PROVIDER` | `ollama` (default), `anthropic`, `gemini` or `openai` |
| `OLLAMA_URL`, `OLLAMA_MODEL` | Ollama server and default model |
| `ANTHROPIC_API_KEY` | Anthropic key (the SDK also picks up an `ant auth login` profile) |
| `GEMINI_API_KEY` | Google AI Studio key |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` | Any OpenAI-compatible endpoint |

API keys saved in Settings are stored in plain text in your local SQLite database (`backend/data/tutor.db`).

### 4. Run the tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest
```

The suite uses a fake LLM, so it needs no model or network. GitHub Actions runs it, along with the frontend lint and build, on every push and pull request.

## 🌐 API Reference Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/documents/upload` | `POST` | Upload PDF/DOCX/PPTX/TXT/MD. A summary and concept map are generated in the background. |
| `/api/documents` · `/api/documents/{id}` | `GET` | List documents, or get one with its summary and concepts. |
| `/api/documents/{id}/summarize` | `POST` | Regenerate a document's summary and concept map. |
| `/api/search?q=` | `GET` | Full-text search with highlighted snippets. |
| `/api/chat/stream` | `POST` | Stream a tutor reply. `X-Session-Id` and `X-Sources` (base64 JSON citations) are sent as headers. |
| `/api/chat/sessions` | `GET` | List saved chats (`?kind=tutor\|mentor`); `GET/PATCH/DELETE /{id}` for one chat. |
| `/api/study/mentor/stream` | `POST` | Stream a mentor reply (same session support). |
| `/api/flashcards/generate` | `POST` | Generate flashcards from a topic or document. |
| `/api/flashcards/due` · `/api/flashcards/{id}/review` | `GET` · `POST` | Get the review queue; submit an SM-2 grade (0–5). |
| `/api/mock-exams` | `POST` · `GET` | Start a timed mock exam; list past exams. |
| `/api/mock-exams/{id}/submit` | `POST` | Submit answers and get a graded report. |
| `/api/quiz/generate` · `/api/quiz/submit` | `POST` | Generate a quiz question; grade an answer. |
| `/api/dashboard` · `/api/dashboard/analytics` | `GET` | Streak, readiness, mastery and its weekly trend. |
| `/api/settings/llm` | `GET` · `PUT` | Active provider/model and masked keys. |
| `/api/settings/llm/models?provider=` | `GET` | Models available from a provider. |
| `/api/settings/llm/health` | `GET` | Whether the active model is reachable. |
| `/api/db/overview` | `GET` | Database table structure and row counts. |

## 📝 Important Notes

*   **Single User Design**: TinyTutor uses user ID `1`. It is designed as a personal, single-student application.
*   **Privacy**: With Ollama, nothing leaves your machine. With a cloud provider, the relevant note excerpts and your questions are sent to that provider.
*   **Efficient AI Execution**: Models run only when requested. The 30-minute scheduler adds one question at a time.
*   **File Limits**: Maximum upload size is 25MB per file.
*   **Upgrading**: Existing databases are migrated automatically on startup. The search index is built from your existing notes, and past quiz answers seed the new mastery scores.

---

**Keywords**: AI Study Tutor, Local AI App, Ollama Next.js, Claude API, Gemini API, FastAPI AI Project, Open Source Exam Monitor, Local RAG, AI Quiz Generator, Spaced Repetition Flashcards, Mock Exam Simulator, AI Learning Platform, Offline Study Tools.
