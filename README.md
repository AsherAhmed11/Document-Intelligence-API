# Document Intelligence API

> A production-grade RAG pipeline for legal document analysis. Upload any PDF, TXT, or DOCX — ask questions in plain English — get cited, grounded answers backed by the exact source chunks that informed them.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python)](https://python.org)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-0.5+-FF6B35?style=flat)](https://www.trychroma.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat&logo=docker)](https://docker.com)

---

## Overview

The Document Intelligence API is a FastAPI-based service that enables semantic search and question-answering over legal documents using a Retrieval-Augmented Generation (RAG) architecture. Documents are parsed, semantically chunked, and embedded into a persistent ChromaDB vector store. At query time, relevant chunks are retrieved, scored, and passed to an LLM with function calling to produce cited answers grounded in the actual document content.

The system is designed for legal document analysis specifically — with semantic chunking tuned for dense legal prose, a curated cross-reference keyword dictionary for multi-hop retrieval, and a two-stage hallucination prevention mechanism that avoids LLM calls entirely when no relevant context exists.

---

## Features

- 📄 **Multi-format document upload** — PDF (PyMuPDF, page-level), TXT, and DOCX
- 🧩 **Semantic chunking, no overlap** — meaning-based splits using LangChain's SemanticChunker; no fixed token counts, no artificial overlap
- 🔍 **Vector similarity search** — ChromaDB-backed retrieval with configurable `top_k`
- 🔗 **Legal cross-reference detection** — curated keyword dictionary triggers targeted metadata-filter queries ("pursuant to Section 3.2", "as defined in Annex A")
- 🔄 **Multi-hop retrieval** — LLM signals intent via function calling; up to 2 retrieval hops, capped at 3 total LLM calls per query
- 🛡️ **Two-stage hallucination prevention** — Stage 1: score threshold check before any LLM call; Stage 2: LLM signals `answer_found: false` via function schema
- 📌 **Inline citations** — answers contain `[1][2]` inline references remapped to a `References:` block with page, section, and excerpt
- ⚙️ **Pluggable providers** — local sentence-transformers, OpenAI, or Bytez for both embeddings and LLM
- 🐳 **Docker-ready** — Railway `PORT` injection handled; `railway.toml` included for one-click deploy

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI + Uvicorn |
| Data Validation | Pydantic v2 + pydantic-settings |
| Vector Store | ChromaDB (persistent) |
| Embeddings | `BAAI/bge-large-en-v1.5` via sentence-transformers (default) |
| Chunking | LangChain `SemanticChunker` (percentile breakpoint) |
| LLM | GPT-4o-mini via OpenAI API (function calling) |
| PDF Parsing | PyMuPDF (fitz) |
| DOCX Parsing | python-docx |
| HTTP Client | httpx |
| Testing | pytest + FastAPI TestClient |
| Containerization | Docker (python:3.11-slim) |
| Deployment | Railway (via `railway.toml`) |

---

## Project Structure

```
document-intelligence-api/
│
├── app/
│   ├── main.py                   # FastAPI app: router registration, CORS, global error handler
│   ├── config.py                 # Typed settings via pydantic-settings (reads .env)
│   │
│   ├── core/                     # Low-level processing engine
│   │   ├── chunker.py            # Text extraction (PDF/TXT/DOCX) + semantic chunking
│   │   ├── cross_ref.py          # Legal cross-reference keyword detector
│   │   └── embeddings.py         # EmbeddingClient: local / OpenAI / Bytez
│   │
│   ├── models/                   # Pydantic request & response schemas
│   │   ├── document.py           # DocumentUploadResponse, DocumentMetadataResponse
│   │   └── query.py              # QueryRequest, QueryResponse, Citation
│   │
│   ├── routers/                  # HTTP layer — routing only, no business logic
│   │   ├── health.py             # GET /health
│   │   ├── documents.py          # POST /upload, GET /{id}, DELETE /{id}
│   │   └── query.py              # POST /{id}/query
│   │
│   └── services/                 # Business logic layer
│       ├── document_service.py   # Full upload pipeline: extract → chunk → embed → index
│       └── query_service.py      # Full RAG pipeline: search → score → LLM → cite
│
├── tests/
│   ├── conftest.py               # Pytest fixtures (TestClient, Settings)
│   └── test_query.py             # Integration tests: upload → query → delete lifecycle
│
├── scripts/
│   └── compare_embeddings.py     # Offline embedding model comparison (BGE-Large vs MiniLM)
│
├── test_docs/
│   └── sample_legal_agreement.txt
│
├── .env.example                  # Environment variable template
├── .gitignore
├── requirements.txt
├── Dockerfile
├── railway.toml                  # Railway deployment config
├── DEPLOY.md                     # Step-by-step Railway deployment guide
└── DELEGATION_PLAN.md            # Architecture decision log
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- An OpenAI API key (`gpt-4o-mini` for LLM calls)
- Git

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/document-intelligence-api.git
cd document-intelligence-api

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY (minimum required)

# 5. Run the development server
uvicorn app.main:app --reload
```

The API is now running at **http://localhost:8000**

Open **http://localhost:8000/docs** for the interactive Swagger UI.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/documents/upload` | Upload a PDF, TXT, or DOCX file. Returns a `document_id` to use in subsequent requests. |
| `GET` | `/documents/{document_id}` | Retrieve metadata for a previously uploaded document (filename, chunk count, status). |
| `DELETE` | `/documents/{document_id}` | Remove a document and all its associated vectors from ChromaDB. |
| `POST` | `/documents/{document_id}/query` | Ask a natural-language question. Returns an LLM-generated answer with inline `[N]` citations and a `References:` block. |
| `GET` | `/health` | Health check — returns `{"status": "ok"}`. Used by Railway for liveness checks. |
| `GET` | `/docs` | Interactive Swagger UI (auto-generated). |
| `GET` | `/redoc` | ReDoc API documentation. |

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | **Required for LLM calls.** Your OpenAI API key. |
| `BYTEZ_API_KEY` | — | Optional. Alternative provider for LLM and embeddings. |
| `LLM_PROVIDER` | `openai` | LLM backend: `openai` or `bytez` |
| `LLM_MODEL` | `gpt-4o-mini` | Model identifier for the LLM provider |
| `EMBEDDING_PROVIDER` | `local` | Embedding backend: `local`, `openai`, or `bytez` |
| `EMBEDDING_MODEL` | `BAAI/bge-large-en-v1.5` | Model name. For local: any sentence-transformers model. |
| `DEBUG` | `false` | Set `true` to include full error details in responses (development only) |
| `CHROMA_PERSIST_DIRECTORY` | `./chroma_store` | Path where ChromaDB persists its data |
| `CHROMA_COLLECTION_NAME` | `documents` | ChromaDB collection name prefix |
| `MAX_UPLOAD_SIZE_MB` | `20` | Maximum allowed file upload size |

### Switching Embedding Providers

```bash
# Use local BGE-Large (default — free, offline, best accuracy)
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5

# Use OpenAI embeddings
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=sk-...

# Use Bytez
EMBEDDING_PROVIDER=bytez
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
BYTEZ_API_KEY=your-key
```

---

## Example Usage

### 1. Upload a Document

```bash
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@path/to/contract.pdf"
```

**Response:**
```json
{
  "document_id": "doc_a1b2c3d4",
  "filename": "contract.pdf",
  "status": "ready",
  "chunk_count": 23
}
```

### 2. Query the Document

```bash
curl -X POST http://localhost:8000/documents/doc_a1b2c3d4/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the indemnification obligations and how do they relate to payments?",
    "top_k": 5
  }'
```

**Response:**
```json
{
  "document_id": "doc_a1b2c3d4",
  "question": "What are the indemnification obligations...",
  "answer": "The licensor bears full indemnification responsibility [1]. Pursuant to Section 3.2, the seller shall indemnify the buyer against any liability arising from the services [2].\n\nReferences:\n[1] Page 3, §3.2 — \"The licensor shall indemnify the licensee...\"\n[2] Page 7 — \"Obligations set forth herein apply concurrently...\"",
  "citations": [
    {
      "chunk_index": 4,
      "page_number": 3,
      "excerpt": "The licensor shall indemnify the licensee against all claims...",
      "relevance_score": 0.91
    }
  ],
  "answer_found": true
}
```

### 3. Delete the Document

```bash
curl -X DELETE http://localhost:8000/documents/doc_a1b2c3d4
```

---

## Testing

```bash
# Run the full test suite
pytest tests/ -v

# Run a specific test
pytest tests/test_query.py::test_document_lifecycle_and_rag_query -v
```

The integration test (`test_document_lifecycle_and_rag_query`) covers the complete lifecycle:
1. Upload a document with cross-references
2. Get document metadata
3. Query with a relevant question — verifies `answer_found: true`, citations, and `References:` block
4. Query with an irrelevant question — verifies Stage 1 threshold filters it (`answer_found: false`)
5. Delete the document
6. Verify 404 after deletion

---

## Deployment

See **[DEPLOY.md](DEPLOY.md)** for complete step-by-step Railway deployment instructions, including:
- Pushing to GitHub safely (no secrets committed)
- Setting environment variables in the Railway dashboard
- Generating a public URL
- Troubleshooting cold-start delays with BGE-Large

**TL;DR:**
```bash
# Push to GitHub
git push origin main

# Railway: New Project → Deploy from GitHub → pick your repo
# Set env vars in Railway Variables tab (OPENAI_API_KEY, LLM_MODEL, etc.)
# Railway auto-detects Dockerfile + railway.toml → deploys
```

---

## Architecture Decisions

All key architecture choices — chunking strategy, embedding model selection, retrieval design, citation format, and hallucination prevention — are documented with full reasoning in **[DELEGATION_PLAN.md](DELEGATION_PLAN.md)**.

Key decisions at a glance:

| Decision | Choice | Reasoning |
|---|---|---|
| Chunking | Semantic, no overlap | Overlap is a fixed-size artifact; semantic chunking doesn't fragment sentences |
| Breakpoint threshold | 95th percentile | Dense legal prose needs fewer, larger, more coherent chunks |
| Embedding model | `BAAI/bge-large-en-v1.5` | Empirically tested vs BGE-Base and MiniLM on actual legal documents |
| Retrieval | Vector similarity + cross-ref routing | Legal docs have explicit section references — metadata filters beat similarity for targeted hops |
| LLM control | Function calling | Allows LLM to signal intent ("fetch Section 3.2"), not just return text — JSON mode doesn't constrain schema |
| Max hops | 2 | Bounds total LLM calls at 3 per query; marginal value drops sharply beyond 2 hops |
| Score threshold | 0.40 | Calibrated empirically: correct matches score 0.48–0.50, irrelevant retrievals below 0.30 |

---

## License

MIT
