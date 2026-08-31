# Document Intelligence API & Web App

> A high-performance, production-grade Document Intelligence RAG web application built with **FastAPI**, **Google Gemini API** (`gemini-3.6-flash` + `gemini-embedding-001`), and **ChromaDB**. Upload PDF, TXT, or DOCX files — ask questions — get cited answers backed by exact source excerpts and general knowledge verification.

---

## 🌟 Key Features

- ⚡ **Google Gemini Integration** — Uses `gemini-embedding-001` (768-dim) for embeddings and `gemini-3.6-flash` for high-speed Q&A with zero local RAM footprint.
- 🎨 **Modern Dark Web UI** — Built-in glassmorphism web interface with drag-and-drop upload, dynamic citation chips, instant document switching, and smooth scroll controls.
- 💬 **New Chat & Session Management** — Clear chat history or start fresh conversations per document at any time.
- 💡 **General Knowledge Fallback with Verification Sources** — If an answer is not present in your document, Gemini provides a general knowledge response with clear notice and 2-3 standard authoritative verification references (e.g. Legal Institutes, Black's Law, official specs).
- 📌 **Cited Answers & Modal Excerpts** — Inline `[1]`, `[2]` citations with clickable source chips that pop open the exact paragraph excerpt and page number.
- 🔗 **Cross-Reference Resolution** — Automatically resolves legal cross-references ("pursuant to Section 3.2").
- 🐳 **Railway Free-Tier Ready** — Zero local PyTorch models required; deploys in seconds on Railway's 512MB free tier with a single `GEMINI_API_KEY`.

---

## 🏗️ Architecture

```
Document Intelligence API
├── app/
│   ├── main.py                   # FastAPI app & static file mounting
│   ├── config.py                 # Pydantic settings & environment configuration
│   ├── core/
│   │   ├── chunker.py            # Text extraction (PDF/TXT/DOCX) + paragraph-aware chunker
│   │   ├── cross_ref.py          # Legal cross-reference pattern detector
│   │   └── embeddings.py         # Gemini / OpenAI embedding client wrapper
│   ├── models/
│   │   ├── document.py           # Upload & document metadata Pydantic models
│   │   └── query.py              # Query request, response, and citation schemas
│   ├── routers/
│   │   ├── health.py             # Health check GET /health
│   │   ├── documents.py          # Upload, list, metadata, delete endpoints
│   │   └── query.py              # Vector query endpoint
│   └── services/
│       ├── document_service.py   # Document parsing, chunking & ChromaDB indexing
│       └── query_service.py      # RAG pipeline, cross-ref hops & general knowledge fallback
├── frontend/
│   ├── index.html                # Modern single-page web app interface
│   ├── style.css                 # Vanilla CSS design system
│   └── app.js                    # Reactive frontend app logic & API calls
├── test_docs/                    # Sample test legal documents
├── requirements.txt              # Application dependencies
└── Dockerfile                    # Container definition
```

---

## 🚀 Quick Start (Local Setup)

### Prerequisites

- Python 3.11+
- Free Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/apikey) (takes 30 seconds)

### 1. Clone & Install

```bash
git clone https://github.com/AsherAhmed11/Document-Intelligence-API.git
cd Document-Intelligence-API

python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Set Environment Variables

Create `.env` file:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.6-flash
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=gemini-embedding-001
```

### 3. Run Application

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Open **http://localhost:8000** in your browser to use the Web Application.
- Open **http://localhost:8000/docs** for the interactive Swagger API documentation.

---

## 🚢 Deployment (Railway)

1. Push code to your GitHub repository.
2. In [Railway](https://railway.app), click **New Project** → **Deploy from GitHub repo**.
3. In **Variables**, set:
   ```
   GEMINI_API_KEY = your_gemini_api_key_here
   ```
4. Railway will automatically build the Docker container and deploy!

---

## 📄 License

MIT License
