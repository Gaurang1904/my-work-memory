import logging
import re

from sqlalchemy import Select, and_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.schemas.query import QueryFilters
from app.services.embeddings import EmbeddingService


logger = logging.getLogger(__name__)
settings = get_settings()


def retrieve_chunks(
    db: Session,
    query: str,
    filters: QueryFilters | None = None,
    top_k: int = 5,
) -> list[tuple[Chunk, Document, float]]:
    """Semantic retrieval: embed the query, rank chunks by cosine distance,
    apply optional metadata filters and a distance threshold, and deduplicate.

    Intent routing (e.g. "list projects" vs "how much experience") is handled
    upstream by the agent's tools, so this stays a clean vector search with no
    query-specific heuristics.
    """
    embedding_service = EmbeddingService()
    query_embedding = embedding_service.embed_query(query)
    distance_expr = Chunk.embedding.cosine_distance(query_embedding).label("distance")
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

    logger.info("Retrieval complete: query=%r returned=%s", query, len(deduped))
    return deduped
