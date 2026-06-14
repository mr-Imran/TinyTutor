# TinyTutor: The Ultimate Local-First AI Study Tutor & Exam Monitor

**TinyTutor** is a powerful, local-first **AI study tutor** and **exam monitor** designed to help students, developers, and lifelong learners master any subject. By leveraging local Large Language Models (LLMs) via **Ollama**, TinyTutor allows you to upload course materials (PDFs, PPTX), chat securely with your documents, generate custom AI quizzes, and track your learning progress—all optimized for low-end hardware without relying on expensive cloud APIs.

## 🚀 Key Features

*   **📚 Local Document Chat (RAG)**: Upload PDF and PPTX files. The built-in document processor chunks your data into SQLite. Chat directly with your materials using local AI.
*   **🧠 AI-Generated Quizzes**: Automatically generate Multiple Choice (MCQ), True/False, and Short Answer questions based on your uploaded knowledge base. Select from Easy, Medium, or Hard difficulties.
*   **📈 Smart Dashboard & Analytics**: Track your study streaks, overall readiness, and visually analyze your strong and weak topics using interactive Recharts.
*   **🎓 Exam Simulation**: Take comprehensive practice exams to test your knowledge retention under pressure.
*   **⏰ Automated Study Scheduler**: Uses APScheduler to ping you with a study question on your weakest topic every 30 minutes.
*   **🔒 100% Privacy & Local AI**: Powered by Ollama (default `qwen2.5:0.5b`). No data leaves your machine. Perfect for private, offline studying.
*   **🗄️ Built-in Database Viewer**: Easily manage your knowledge base. Add, edit, or delete specific context chunks directly from the UI.

## 🛠️ Technology Stack

TinyTutor is built with a modern, performant, and developer-friendly stack:

*   **Backend**: Python, [FastAPI](https://fastapi.tiangolo.com/), SQLite, [Ollama](https://ollama.com/), APScheduler, PyMuPDF, python-pptx.
*   **Frontend**: [Next.js 15](https://nextjs.org/), React, TypeScript, Tailwind CSS, Framer Motion, shadcn/ui components, Recharts.
*   **AI Engine**: Local LLM inference via Ollama. No vector database required (uses efficient keyword matching).

## 🎯 Who is TinyTutor For?

*   **Students**: Turn lecture slides and textbook PDFs into interactive tutors.
*   **Self-Learners**: Generate quizzes to reinforce learning on any topic.
*   **Developers**: A perfect starter template for building local AI apps with FastAPI and Next.js.

## ⚙️ Prerequisites

Before installing TinyTutor, ensure you have the following installed:

1.  **Python 3.10–3.14** (3.10–3.12 recommended for the smoothest installation)
2.  **Node.js 18+**
3.  **Ollama** — Download at [ollama.com](https://ollama.com)

**Pull the default local model:**
```bash
ollama pull qwen2.5:0.5b
# Alternatively, use gemma3:270m and update backend/config.py
```

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

# Install dependencies and run the server
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
*Access the TinyTutor dashboard at **`http://localhost:3000`***

## 🌐 API Reference Overview

TinyTutor provides a clean RESTful API for integration:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/documents/upload` | `POST` | Upload and process PDF/PPTX materials. |
| `/api/documents` | `GET` | Retrieve a list of uploaded documents. |
| `/api/chat` | `POST` | Chat with the AI tutor grounded in local data. |
| `/api/quiz/generate` | `POST` | Generate an AI quiz question. |
| `/api/quiz/submit` | `POST` | Submit an answer for grading and feedback. |
| `/api/quiz/exam` | `POST` | Initiate a simulated practice exam. |
| `/api/dashboard` | `GET` | Fetch user dashboard statistics (streak, readiness). |
| `/api/dashboard/analytics` | `GET` | Get JSON data for Recharts analytics. |
| `/api/db/overview` | `GET` | View database table structures and row counts. |

## 📝 Important Notes

*   **Single User Design**: TinyTutor defaults to user ID `1`. It is designed as a personal, single-student application.
*   **Efficient AI Execution**: The AI models run only when requested. The 30-minute scheduler triggers standard notifications without continuously draining background resources.
*   **File Limits**: The maximum supported upload size is 25MB per file to ensure smooth local processing.

---

**Keywords**: AI Study Tutor, Local AI App, Ollama Next.js, FastAPI AI Project, Open Source Exam Monitor, Local RAG, AI Quiz Generator, AI Learning Platform, Offline Study Tools.
