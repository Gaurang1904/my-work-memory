import logging
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.chunk import Chunk
from app.models.document import Document
from app.schemas.upload import LocalIngestRequest, RepoFileInfo, UploadResponse
from app.services.auth import require_admin_api
from app.services.chunker import chunk_text
from app.services.embeddings import EmbeddingService
from app.services.extractor import detect_source_type, extract_text
from app.services.vector_store import add_chunks


router = APIRouter(prefix="/upload", tags=["upload"])
settings = get_settings()
logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "project-data" / "raw"
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


@router.post("", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    source_type: str | None = Form(default=None),
    project_name: str | None = Form(default=None),
    company_name: str | None = Form(default=None),
    document_date: date | None = Form(default=None),
    tags: str | None = Form(default=None),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin_api),
) -> UploadResponse:
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    return _ingest_bytes(
        db=db,
        file_name=file.filename or "document",
        file_bytes=file_bytes,
        title=title,
        source_type=source_type,
        project_name=project_name,
        company_name=company_name,
        document_date=document_date,
        tags=_parse_tags(tags),
    )


@router.get("/repo-files", response_model=list[RepoFileInfo])
def list_repo_files(_admin: dict = Depends(require_admin_api)) -> list[RepoFileInfo]:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    files: list[RepoFileInfo] = []
    for path in sorted(RAW_DATA_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        files.append(
            RepoFileInfo(
                file_name=path.name,
                relative_path=str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                size_bytes=path.stat().st_size,
                source_type=detect_source_type(path.name),
            )
        )
    return files


@router.post("/ingest-local", response_model=UploadResponse)
def ingest_local_document(
    payload: LocalIngestRequest,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin_api),
) -> UploadResponse:
    path = _resolve_repo_file(payload.file_name)
    file_bytes = path.read_bytes()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Selected local file is empty.")

    return _ingest_bytes(
        db=db,
        file_name=path.name,
        file_bytes=file_bytes,
        title=payload.title,
        source_type=payload.source_type,
        project_name=payload.project_name,
        company_name=payload.company_name,
        document_date=payload.document_date,
        tags=payload.tags,
    )


@router.post("/ingest-all-local", response_model=list[UploadResponse])
def ingest_all_local_documents(
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin_api),
) -> list[UploadResponse]:
    files = list_repo_files()
    responses: list[UploadResponse] = []

    for file_info in files:
        path = _resolve_repo_file(file_info.file_name)
        file_bytes = path.read_bytes()
        if not file_bytes:
            logger.warning("Skipping empty local file during bulk ingest: %s", file_info.file_name)
            continue

        response = _ingest_bytes(
            db=db,
            file_name=path.name,
            file_bytes=file_bytes,
            title=None,
            source_type=None,
            project_name=None,
            company_name=None,
            document_date=None,
            tags=[],
        )
        responses.append(response)

    return responses


def _ingest_bytes(
    db: Session,
    file_name: str,
    file_bytes: bytes,
    title: str | None,
    source_type: str | None,
    project_name: str | None,
    company_name: str | None,
    document_date: date | None,
    tags: list[str],
) -> UploadResponse:
    embedding_service = EmbeddingService()
    inferred_source_type = detect_source_type(file_name, source_type)
    logger.info("Upload received: filename=%s source_type=%s", file_name, inferred_source_type)

    try:
        raw_text, page_map = extract_text(file_bytes, file_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No extractable text was found in the uploaded file.")

    logger.info("Extraction complete: filename=%s text_length=%s", file_name, len(raw_text))

    existing_document = None
    if hasattr(db, "execute"):
        existing_document = db.execute(
            select(Document)
            .where(Document.title == (title or file_name or "Untitled Document"))
            .where(Document.raw_text == raw_text)
            .order_by(Document.created_at.desc())
        ).scalars().first()

    if existing_document is not None:
        existing_chunks = len(existing_document.chunks)
        logger.info(
            "Duplicate document skipped: document_id=%s filename=%s existing_chunks=%s",
            existing_document.id,
            file_name,
            existing_chunks,
        )
        return UploadResponse(
            document_id=str(existing_document.id),
            title=existing_document.title,
            source_type=existing_document.source_type,
            chunks_created=existing_chunks,
        )

    try:
        document = Document(
            title=title or file_name or "Untitled Document",
            source_type=inferred_source_type,
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
            raise HTTPException(status_code=400, detail="No chunks could be created from the extracted text.")

        logger.info("Chunking complete: document_id=%s chunks=%s", document.id, len(chunk_payloads))

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
        db.commit()

        logger.info("Upload committed: document_id=%s chunks=%s", document.id, len(chunks))

        return UploadResponse(
            document_id=str(document.id),
            title=document.title,
            source_type=document.source_type,
            chunks_created=len(chunks),
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Upload pipeline failed for filename=%s", file_name)
        raise HTTPException(status_code=500, detail=f"Upload processing failed: {exc}") from exc


def _resolve_repo_file(file_name: str) -> Path:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    candidate = (RAW_DATA_DIR / file_name).resolve()
    raw_root = RAW_DATA_DIR.resolve()
    if raw_root not in candidate.parents and candidate != raw_root:
        raise HTTPException(status_code=400, detail="File path must stay inside project-data/raw.")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Local file not found in project-data/raw.")
    if candidate.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported local file type.")
    return candidate


def _parse_tags(tags: str | None) -> list[str]:
    if not tags:
        return []
    return [tag.strip() for tag in tags.split(",") if tag.strip()]
