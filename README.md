# Personal Document Agent

MVP backend for a personal document intelligence system built with FastAPI, Postgres, pgvector, and Gemini.

## What it does

- Upload PDF, DOCX, TXT, and MD files
- Extract text and split it into chunks
- Generate embeddings and store them in Postgres with pgvector
- Retrieve relevant chunks for grounded Q&A
- Generate grounded reports from retrieved context

## Project structure

```text
personal-doc-agent/
├─ app/
│  ├─ main.py
│  ├─ config.py
│  ├─ db.py
│  ├─ models/
│  ├─ schemas/
│  ├─ routes/
│  ├─ services/
│  └─ prompts/
├─ requirements.txt
├─ .env
└─ README.md
```

## Setup

1. Create a Postgres database named `personal_doc_agent`.
2. Run [sql/init.sql](/abs/c:/Users/ASUS/VSCODE/PA/personal-doc-agent/sql/init.sql) against that database to enable `pgvector`.
3. Create a virtual environment and install dependencies:

```bash
pip install -r requirements.txt
```

4. Update `.env` with your Postgres credentials and Gemini API key.
5. Run the app:

```bash
uvicorn app.main:app --reload
```

## Endpoints

- `POST /upload`
- `GET /upload/repo-files`
- `POST /upload/ingest-local`
- `POST /ask`
- `POST /generate-report`
- `GET /health`
- `GET /` (JSON service info)
- `POST /admin/login`, `GET /admin/logout` (admin session for protected ingest/report endpoints)

This is an API-only backend (no bundled web UI); interactive docs are at `/docs`.

## Notes

- The app initializes tables on startup.
- The app no longer creates the `vector` extension at runtime; that belongs in DB setup.
- Gemini embeddings are configured to 1536 dimensions here to match the current pgvector schema.
- This is intentionally plain RAG first. LangChain and LangGraph should come after the core ingestion and retrieval pipeline proves itself.
- Put repo-managed source files in `project-data/raw` and ingest them via the local ingest API (`POST /upload/ingest-local`).