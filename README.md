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

- `POST /ask` — ask a question; answered by the LangGraph agent (semantic search + structured project/skill tools) with grounded, cited responses
- `GET /health`
- `GET /` (JSON service info)

This is an API-only backend (no bundled web UI); interactive docs are at `/docs`.

## Ingestion

Content lives under `project-data/` (gitignored, local only) and is loaded with a
local script — there is no HTTP upload endpoint:

```bash
python -m scripts.ingest --reset
```

- `project-data/raw/` — resume, profile, notes (PDF/DOCX/TXT/MD) → prose chunks
- `project-data/projects/<slug>.md` — a `Project` row + prose
- `project-data/skills.yaml` — `Skill` rows

## Notes

- The app initializes tables on startup.
- The `vector` extension is created in DB setup (`sql/init.sql`), not at runtime.
- Gemini embeddings are 1536-d to match the pgvector schema.
- `POST /ask` runs a LangGraph agent; retrieval internals (chunking, embeddings) are hand-built.