# TinyTutor: The Ultimate Local-First AI Study Tutor & Exam Monitor

**TinyTutor** is a powerful, local-first **AI study tutor** and **exam monitor** designed to help students, developers, and lifelong learners master any subject. Upload course materials (PDF, DOCX, PPTX, TXT, Markdown, photos of notes) or import web articles and YouTube videos, chat with your documents by text or voice with page-level citations, review AI-generated flashcards with spaced repetition, take timed mock exams, and track your learning progress. Run it fully offline with **Ollama**, or plug in **Anthropic Claude**, **Google Gemini**, or any **OpenAI-compatible** API.

## 🚀 Key Features

*   **📚 Document Chat with Citations (RAG)**: Upload PDF, DOCX, PPTX, TXT and Markdown files. Answers cite the exact note they came from (`[1]`, `[2]`) and link straight to the PDF page.
*   **💬 Saved Conversations**: Tutor and mentor chats are saved as sessions. Follow-up questions keep their context, and past chats are one click away.
*   **🔎 Hybrid Search**: SQLite FTS5 keyword search (BM25) fused with embedding search, so questions match your notes by meaning as well as by exact words.
*   **📷 Vision**: Upload photos of handwritten notes or whiteboards. Scanned PDF pages and images are read by your AI model's vision.
*   **🌐 Web & YouTube Import**: Paste a link. Articles are cleaned to their main text, and YouTube videos are imported from their transcript, with citations that jump to the right moment.
*   **🎙️ Voice Tutor**: Ask questions by voice, have answers read aloud, and practise flashcards hands-free (browser speech; Chrome, Edge or Safari).
*   **📝 Auto Summaries & Concept Maps**: Every upload gets an AI summary and a map of key terms and how they connect.
*   **🃏 Spaced-Repetition Flashcards**: Generate flashcards from any topic, document, or your PDF highlights, and review them on an SM-2 schedule. Import and export Anki decks and CSV files.
*   **🗓️ Adaptive Daily Plan**: Each day's checklist is built from your weakest topics, due flashcards, recent uploads and exam date. Export study sessions to your calendar (.ics).
*   **🏆 XP, Levels & Badges**: Earn XP for every answer, review and finished plan task. Set a daily goal and collect 14 badges.
*   **💾 Backup & Restore**: One .zip with your database and every uploaded file.
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
4.  *(Optional)* **Tesseract OCR** for scanned PDFs. PyMuPDF uses it automatically when installed and `TESSDATA_PREFIX` is set. Without it, scanned pages go to your AI model's vision.
5.  *(Optional)* **An embedding model** for search by meaning: `ollama pull nomic-embed-text`. With Gemini or an OpenAI-compatible provider, their embedding APIs are used instead. Without one, search uses keywords only.
6.  *(Optional)* **A vision model** for photos and scanned pages. Claude, Gemini and GPT-4-class models can see images. With Ollama, pull a vision model such as `qwen2.5vl` and set it under Settings → AI Model.

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
| `/api/documents/import-url` | `POST` | Import a web article, YouTube transcript, or linked file. |
| `/api/search?q=` | `GET` | Hybrid keyword + meaning search with highlighted snippets. |
| `/api/chat/stream` | `POST` | Stream a tutor reply. `X-Session-Id` and `X-Sources` (base64 JSON citations) are sent as headers. |
| `/api/chat/sessions` | `GET` | List saved chats (`?kind=tutor\|mentor`); `GET/PATCH/DELETE /{id}` for one chat. |
| `/api/study/mentor/stream` | `POST` | Stream a mentor reply (same session support). |
| `/api/flashcards/generate` | `POST` | Generate flashcards from a topic or document. |
| `/api/flashcards/due` · `/api/flashcards/{id}/review` | `GET` · `POST` | Get the review queue; submit an SM-2 grade (0–5). |
| `/api/flashcards/from-highlights` | `POST` | Turn a document's highlights and notes into flashcards. |
| `/api/plan/today` · `/api/plan/tasks/{id}/toggle` | `GET` · `POST` | Today's study plan; tick a task off. |
| `/api/plan/calendar.ics` | `GET` | Study sessions as a calendar file (`days`, `hour`, `minute`). |
| `/api/progress` | `GET` | XP, level, daily goal, weekly XP and badges. |
| `/api/data/backup` · `/api/data/restore` | `GET` · `POST` | Download or restore a full backup (.zip). |
| `/api/data/flashcards.apkg` · `.csv` · `/api/data/flashcards/import` | `GET` · `POST` | Anki/CSV export and import. |
| `/api/mock-exams` | `POST` · `GET` | Start a timed mock exam; list past exams. |
| `/api/mock-exams/{id}/submit` | `POST` | Submit answers and get a graded report. |
| `/api/quiz/generate` · `/api/quiz/submit` | `POST` | Generate a quiz question; grade an answer. |
| `/api/dashboard` · `/api/dashboard/analytics` | `GET` | Streak, readiness, mastery and its weekly trend. |
| `/api/settings/llm` | `GET` · `PUT` | Active provider/model and masked keys. |
| `/api/settings/llm/models?provider=` | `GET` | Models available from a provider. |
| `/api/settings/llm/health` | `GET` | Whether the active model is reachable. |
| `/api/settings/embeddings` · `/reindex` | `GET` · `PUT` · `POST` | Embedding provider/model and search index status; build the index. |
| `/api/settings/vision` | `GET` · `PUT` | Optional separate vision model per provider. |
| `/api/db/overview` | `GET` | Database table structure and row counts. |

## 📝 Important Notes

*   **Single User Design**: TinyTutor uses user ID `1`. It is designed as a personal, single-student application.
*   **Privacy**: With Ollama, nothing leaves your machine. With a cloud provider, the relevant note excerpts, your questions and any images you upload are sent to that provider. Voice features use your browser's speech engine, which may process audio in the cloud (Chrome does).
*   **Restoring a backup** replaces all current data. A safety copy of the previous database is kept as `backend/data/pre-restore-<time>.db`.
*   **Efficient AI Execution**: Models run only when requested. The 30-minute scheduler adds one question at a time.
*   **File Limits**: Maximum upload size is 25MB per file.
*   **Upgrading**: Existing databases are migrated automatically on startup. The search index is built from your existing notes, and past quiz answers seed the new mastery scores.

---

**Keywords**: AI Study Tutor, Local AI App, Ollama Next.js, Claude API, Gemini API, FastAPI AI Project, Open Source Exam Monitor, Local RAG, Hybrid Semantic Search, AI Quiz Generator, Spaced Repetition Flashcards, Anki Export, YouTube Transcript Notes, Voice Tutor, Study Planner, Mock Exam Simulator, AI Learning Platform, Offline Study Tools.
