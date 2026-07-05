"""Local knowledge-base ingestion.

Run from the repo root:

    python -m scripts.ingest                 # ingest everything
    python -m scripts.ingest --reset         # drop + recreate tables first
    python -m scripts.ingest --only skills   # subset: projects,skills,raw

Content lives under project-data/ (gitignored, local only):

    project-data/raw/<file>.pdf|docx|txt|md   -> prose documents (resume, notes)
    project-data/projects/<slug>.md           -> a Project row + prose chunks
    project-data/skills.yaml                  -> Skill rows

A project markdown file looks like:

    ---
    slug: crypto-forecasting
    name: Crypto Price Forecasting
    summary: Short-term BTC/ETH forecasting with LSTMs and a backtesting harness.
    category: Machine Learning
    tech_stack: [Python, PyTorch, pandas]
    tags: [time-series, deep-learning]
    github_url: https://github.com/you/crypto-forecasting
    start_date: 2024-06-01
    end_date: 2024-09-01
    is_featured: true
    ---

    ## Overview
    Prose here becomes chunks linked to this project...
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml

# Make the repo root importable whether run as `-m scripts.ingest` or directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import app.models  # noqa: E402,F401  (registers all models on Base.metadata)
from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.services.embeddings import EmbeddingService  # noqa: E402
from app.services.extractor import detect_source_type, extract_text  # noqa: E402
from app.services.ingest import ingest_document, upsert_project, upsert_skill  # noqa: E402


logger = logging.getLogger("ingest")

CONTENT_ROOT = REPO_ROOT / "project-data"
RAW_DIR = CONTENT_ROOT / "raw"
PROJECTS_DIR = CONTENT_ROOT / "projects"
SKILLS_FILE = CONTENT_ROOT / "skills.yaml"
SUPPORTED_RAW = {".pdf", ".docx", ".txt", ".md"}


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a markdown file into (frontmatter dict, body str)."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return yaml.safe_load(parts[1]) or {}, parts[2].strip()
    return {}, text.strip()


def ingest_projects(db, embedding_service: EmbeddingService) -> int:
    if not PROJECTS_DIR.is_dir():
        logger.info("No projects directory at %s; skipping.", PROJECTS_DIR)
        return 0

    count = 0
    for path in sorted(PROJECTS_DIR.glob("*.md")):
        if path.name.startswith("_"):
            continue  # templates / drafts (e.g. _template.md) are not ingested
        meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        if not all(meta.get(key) for key in ("slug", "name", "summary")):
            logger.warning("Skipping %s: frontmatter needs slug, name, and summary.", path.name)
            continue

        upsert_project(db, meta)
        if body:
            ingest_document(
                db,
                title=meta["name"],
                source_type="project",
                raw_text=body,
                page_map=[{"page_number": None, "text": body}],
                project_name=meta["slug"],
                tags=list(meta.get("tags") or []),
                embedding_service=embedding_service,
            )
        count += 1

    logger.info("Projects processed: %s", count)
    return count


def ingest_skills(db) -> int:
    if not SKILLS_FILE.is_file():
        logger.info("No skills file at %s; skipping.", SKILLS_FILE)
        return 0

    entries = yaml.safe_load(SKILLS_FILE.read_text(encoding="utf-8")) or []
    processed = 0
    for entry in entries:
        if not entry.get("name"):
            logger.warning("Skipping skill with no name: %r", entry)
            continue
        upsert_skill(db, entry)
        processed += 1

    logger.info("Skills processed: %s", processed)
    return processed


def ingest_raw(db, embedding_service: EmbeddingService) -> int:
    if not RAW_DIR.is_dir():
        logger.info("No raw directory at %s; skipping.", RAW_DIR)
        return 0

    count = 0
    for path in sorted(RAW_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_RAW:
            continue
        raw_text, page_map = extract_text(path.read_bytes(), path.name)
        document = ingest_document(
            db,
            title=path.stem,
            source_type=detect_source_type(path.name),
            raw_text=raw_text,
            page_map=page_map,
            embedding_service=embedding_service,
        )
        if document is not None:
            count += 1

    logger.info("Raw documents processed: %s", count)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the local knowledge base.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables first.")
    parser.add_argument("--only", default="", help="Comma-separated subset: projects,skills,raw")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    if args.reset:
        logger.warning("Resetting database: dropping all tables.")
        Base.metadata.drop_all(bind=engine)

    init_db()

    steps = {s.strip() for s in args.only.split(",") if s.strip()} or {"projects", "skills", "raw"}
    embedding_service = EmbeddingService() if steps & {"projects", "raw"} else None

    db = SessionLocal()
    try:
        if "projects" in steps:
            ingest_projects(db, embedding_service)
        if "skills" in steps:
            ingest_skills(db)
        if "raw" in steps:
            ingest_raw(db, embedding_service)
        db.commit()
        logger.info("Ingestion committed.")
    except Exception:
        db.rollback()
        logger.exception("Ingestion failed; rolled back.")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
