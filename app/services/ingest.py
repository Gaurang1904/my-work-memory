"""Reusable ingestion primitives.

These are the building blocks for loading the curated knowledge base into the
database. They are called by the local ``scripts/ingest.py`` CLI (the intended
path) and reuse the same extract -> chunk -> embed -> store pipeline the app
already relies on. Nothing here touches HTTP; ingestion is a local operation.
"""

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.project import Project
from app.models.skill import Skill
from app.services.chunker import chunk_text
from app.services.embeddings import EmbeddingService
from app.services.vector_store import add_chunks


logger = logging.getLogger(__name__)
settings = get_settings()


def ingest_document(
    db: Session,
    *,
    title: str,
    source_type: str,
    raw_text: str,
    page_map: list[dict],
    project_name: str | None = None,
    company_name: str | None = None,
    document_date: date | None = None,
    tags: list[str] | None = None,
    embedding_service: EmbeddingService | None = None,
) -> Document | None:
    """Chunk, embed, and store one document. Returns None if there was no text.

    Deduplicates on (title, raw_text): re-running ingestion on unchanged content
    is a no-op, so the script is safe to run repeatedly.
    """
    tags = tags or []
    if not raw_text.strip():
        logger.warning("Skipping document with no extractable text: %s", title)
        return None

    embedding_service = embedding_service or EmbeddingService()

    existing = db.execute(
        select(Document)
        .where(Document.title == title)
        .where(Document.raw_text == raw_text)
        .order_by(Document.created_at.desc())
    ).scalars().first()
    if existing is not None:
        logger.info("Duplicate document skipped: %s (%s chunks)", title, len(existing.chunks))
        return existing

    document = Document(
        title=title,
        source_type=source_type,
        project_name=project_name,
        company_name=company_name,
        document_date=document_date,
        tags=tags,
        raw_text=raw_text,
    )
    db.add(document)
    db.flush()

    chunk_payloads = chunk_text(page_map, settings.chunk_size, settings.chunk_overlap)
    if not chunk_payloads:
        logger.warning("No chunks produced for document: %s", title)
        return document

    embeddings = embedding_service.embed_texts([item["chunk_text"] for item in chunk_payloads])
    chunks = [
        Chunk(
            document_id=document.id,
            chunk_index=payload["chunk_index"],
            chunk_text=payload["chunk_text"],
            page_number=payload["page_number"],
            section_title=payload["section_title"],
            embedding=embedding,
        )
        for payload, embedding in zip(chunk_payloads, embeddings, strict=True)
    ]
    add_chunks(db, chunks)
    logger.info("Ingested document '%s' with %s chunks", title, len(chunks))
    return document


def upsert_project(db: Session, data: dict) -> Project:
    """Create or update a Project keyed by its slug."""
    slug = data["slug"]
    fields = {
        "name": data["name"],
        "summary": data["summary"],
        "description": data.get("description"),
        "category": data.get("category"),
        "tech_stack": list(data.get("tech_stack") or []),
        "tags": list(data.get("tags") or []),
        "github_url": data.get("github_url"),
        "demo_url": data.get("demo_url"),
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
        "is_featured": bool(data.get("is_featured", False)),
    }

    project = db.execute(select(Project).where(Project.slug == slug)).scalars().first()
    if project is None:
        project = Project(slug=slug, **fields)
        db.add(project)
        logger.info("Created project: %s", slug)
    else:
        for key, value in fields.items():
            setattr(project, key, value)
        logger.info("Updated project: %s", slug)
    db.flush()
    return project


def upsert_skill(db: Session, data: dict) -> Skill:
    """Create or update a Skill keyed by its name."""
    name = data["name"]
    fields = {
        "category": data.get("category"),
        "proficiency": data.get("proficiency"),
        "related_project_slugs": list(data.get("related_project_slugs") or []),
        "notes": data.get("notes"),
    }

    skill = db.execute(select(Skill).where(Skill.name == name)).scalars().first()
    if skill is None:
        skill = Skill(name=name, **fields)
        db.add(skill)
        logger.info("Created skill: %s", name)
    else:
        for key, value in fields.items():
            setattr(skill, key, value)
        logger.info("Updated skill: %s", name)
    db.flush()
    return skill
