import logging
import re
from datetime import date

from sqlalchemy import Select, and_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.schemas.query import QueryFilters
from app.services.embeddings import EmbeddingService


logger = logging.getLogger(__name__)
settings = get_settings()
TEMPORAL_QUERY_PATTERNS = (
    "current",
    "currently",
    "recent",
    "recently",
    "latest",
    "most recent",
    "right now",
    "ongoing",
    "in progress",
    "working on",
    "still working",
)
EXPERIENCE_QUERY_PATTERNS = (
    "work experience",
    "how much experience",
    "how many years",
    "how many months",
    "how long have",
    "experience do you have",
)
TEMPORAL_CHUNK_PATTERNS = (
    "currently",
    "current status",
    "current work",
    "ongoing",
    "in progress",
    "remaining work",
    "future plan",
    "active development",
    "currently in development",
    "currently in internal testing",
    "pending production release",
    "final development stages",
    "most recent",
)
EXPERIENCE_CHUNK_PATTERNS = (
    "experience",
    "reporting period",
    "from ",
    "start date",
    "transitioned to full-time",
    "full-time commitment",
    "hours/week",
    "august",
    "september",
    "october",
    "november",
    "december",
    "january",
    "february",
    "march",
)
EXPERIENCE_DOCUMENT_PATTERNS = (
    "resume",
    "cv",
)


def retrieve_chunks(
    db: Session,
    query: str,
    filters: QueryFilters | None = None,
    top_k: int = 5,
) -> list[tuple[Chunk, Document, float]]:
    embedding_service = EmbeddingService()
    query_embedding = embedding_service.embed_query(query)
    distance_expr = Chunk.embedding.cosine_distance(query_embedding).label("distance")
    temporal_query = _is_temporal_query(query)
    experience_query = _is_experience_query(query)
    candidate_limit = max(top_k, min(max(top_k * 4, 10), 24))

    stmt: Select = (
        select(Chunk, Document, distance_expr)
        .join(Document, Chunk.document_id == Document.id)
        .order_by(distance_expr)
        .limit(candidate_limit)
    )

    clauses = []
    if filters:
        if filters.project_name:
            clauses.append(Document.project_name == filters.project_name)
        if filters.company_name:
            clauses.append(Document.company_name == filters.company_name)
        if filters.source_type:
            clauses.append(Document.source_type == filters.source_type)
        if filters.date_from:
            clauses.append(Document.document_date >= filters.date_from)
        if filters.date_to:
            clauses.append(Document.document_date <= filters.date_to)
        if filters.tags:
            clauses.append(Document.tags.overlap(filters.tags))

    if clauses:
        stmt = stmt.where(and_(*clauses))

    rows = list(db.execute(stmt).all())

    if settings.retrieval_max_distance is not None:
        rows = [row for row in rows if row[2] <= settings.retrieval_max_distance]

    if temporal_query or experience_query:
        rows = sorted(
            rows,
            key=lambda row: _query_rerank_score(row[0], row[1], float(row[2]), temporal_query, experience_query),
            reverse=True,
        )

    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[Chunk, Document, float]] = []
    for chunk, doc, distance in rows:
        normalized_chunk = re.sub(r"\s+", " ", chunk.chunk_text).strip().lower()
        key = (doc.title.strip().lower(), normalized_chunk)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((chunk, doc, float(distance)))
        if len(deduped) >= top_k:
            break

    if deduped:
        distances = [distance for _, _, distance in deduped]
        logger.info(
            "Retrieval complete: query=%r returned=%s min_distance=%.4f max_distance=%.4f threshold=%s temporal_query=%s",
            query,
            len(deduped),
            min(distances),
            max(distances),
            settings.retrieval_max_distance,
            temporal_query,
        )
    else:
        logger.info(
            "Retrieval complete: query=%r returned=0 threshold=%s temporal_query=%s",
            query,
            settings.retrieval_max_distance,
            temporal_query,
        )

    return deduped


def _is_temporal_query(query: str) -> bool:
    normalized = query.lower()
    return any(pattern in normalized for pattern in TEMPORAL_QUERY_PATTERNS)


def _is_experience_query(query: str) -> bool:
    normalized = query.lower()
    return any(pattern in normalized for pattern in EXPERIENCE_QUERY_PATTERNS)


def _query_rerank_score(
    chunk: Chunk,
    document: Document,
    distance: float,
    temporal_query: bool,
    experience_query: bool,
) -> float:
    score = 1.0 - distance
    if temporal_query:
        score = _temporal_rerank_score(chunk, document, distance)
    if experience_query:
        score += _experience_rerank_bonus(chunk, document)
    return score


def _temporal_rerank_score(chunk: Chunk, document: Document, distance: float) -> float:
    score = 1.0 - distance
    text = chunk.chunk_text.lower()

    for pattern in TEMPORAL_CHUNK_PATTERNS:
        if pattern in text:
            score += 0.08

    if chunk.page_number is not None:
        score += min(chunk.page_number, 30) * 0.002

    if document.document_date is not None:
        score += _document_date_bonus(document.document_date)

    return score


def _experience_rerank_bonus(chunk: Chunk, document: Document) -> float:
    score = 0.0
    text = chunk.chunk_text.lower()
    title = document.title.lower()

    for pattern in EXPERIENCE_CHUNK_PATTERNS:
        if pattern in text:
            score += 0.06

    for pattern in EXPERIENCE_DOCUMENT_PATTERNS:
        if pattern in title:
            score += 0.18

    if "experience" in title:
        score += 0.12

    if re.search(r"\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4}\b", chunk.chunk_text):
        score += 0.1

    if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}\s*[–—-]\s*(?:present|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})\b", text):
        score += 0.22

    if document.document_date is not None:
        score += _document_date_bonus(document.document_date) * 0.5

    return score


def _document_date_bonus(document_date: date) -> float:
    baseline = date(2024, 1, 1)
    days_since_baseline = max((document_date - baseline).days, 0)
    return min(days_since_baseline / 3650.0, 0.18)
