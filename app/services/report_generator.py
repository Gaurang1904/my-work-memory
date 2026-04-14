import logging
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from sqlalchemy.orm import Session

from app.config import get_settings
from app.schemas.query import QueryFilters
from app.schemas.query import SourceReference
from app.schemas.report import ReportResponse
from app.services.generation_errors import GenerationTemporarilyUnavailableError
from app.services.retrieval import retrieve_chunks


logger = logging.getLogger(__name__)
settings = get_settings()
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "report_prompt.txt"


def _is_temporary_generation_error(exc: Exception) -> bool:
    message = str(exc).upper()
    return "503" in message or "UNAVAILABLE" in message or "HIGH DEMAND" in message


def _is_quota_generation_error(exc: Exception) -> bool:
    message = str(exc).upper()
    return "429" in message or "RESOURCE_EXHAUSTED" in message or "QUOTA" in message


def generate_report(
    db: Session,
    report_type: str,
    topic: str,
    filters: QueryFilters | None,
) -> ReportResponse:
    if not settings.gemini_api_key.strip():
        raise RuntimeError("GEMINI_API_KEY is missing.")

    retrieval_query = f"{report_type}: {topic}"
    results = retrieve_chunks(db, retrieval_query, filters, settings.max_report_chunks)

    if not results:
        logger.info("No grounded evidence found for report_type=%s topic=%r", report_type, topic)
        return ReportResponse(
            title=_derive_title(report_type),
            report="I don't have enough evidence in the uploaded documents to generate this report.",
            sources=[],
        )

    client = genai.Client(api_key=settings.gemini_api_key)

    sources = [
        SourceReference(
            document=doc.title,
            document_id=str(doc.id),
            chunk_index=chunk.chunk_index,
            page_number=chunk.page_number,
            section_title=chunk.section_title,
            excerpt=chunk.chunk_text[:240],
        )
        for chunk, doc, _distance in results
    ]

    grouped_context = []
    for chunk, doc, distance in results:
        grouped_context.append(
            "\n".join(
                [
                    f"Title: {doc.title}",
                    f"Project: {doc.project_name}",
                    f"Company: {doc.company_name}",
                    f"Date: {doc.document_date}",
                    f"Tags: {', '.join(doc.tags or [])}",
                    f"Chunk Index: {chunk.chunk_index}",
                    f"Distance: {distance}",
                    f"Content: {chunk.chunk_text}",
                ]
            )
        )

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = prompt_template.format(
        report_type=report_type,
        topic=topic,
        context="\n\n---\n\n".join(grouped_context),
    )

    logger.info("Generating report with %s grounded chunks", len(results))

    try:
        response = client.models.generate_content(
            model=settings.gemini_chat_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                system_instruction=(
                    "Generate a grounded report using only the supplied context. "
                    "Do not invent achievements or unsupported details."
                ),
            ),
        )
    except genai_errors.ServerError as exc:
        if _is_quota_generation_error(exc):
            logger.warning("Gemini report generation quota exhausted")
            raise GenerationTemporarilyUnavailableError(
                "Report quota hit for Gemini right now. Wait a bit, or switch to paid quota / another model."
            ) from exc
        if getattr(exc, "status_code", None) == 503 or _is_temporary_generation_error(exc):
            logger.warning("Gemini report generation temporarily unavailable")
            raise GenerationTemporarilyUnavailableError(
                "The report model is temporarily busy. Please try generating the report again in a minute."
            ) from exc
        logger.exception("Report generation failed")
        raise RuntimeError(f"Report generation failed: {exc}") from exc
    except Exception as exc:
        if _is_quota_generation_error(exc):
            logger.warning("Gemini report generation quota exhausted")
            raise GenerationTemporarilyUnavailableError(
                "Report quota hit for Gemini right now. Wait a bit, or switch to paid quota / another model."
            ) from exc
        if _is_temporary_generation_error(exc):
            logger.warning("Gemini report generation temporarily unavailable")
            raise GenerationTemporarilyUnavailableError(
                "The report model is temporarily busy. Please try generating the report again in a minute."
            ) from exc
        logger.exception("Report generation failed")
        raise RuntimeError(f"Report generation failed: {exc}") from exc

    title = _derive_title(report_type)
    return ReportResponse(title=title, report=(response.text or "").strip(), sources=sources)


def _derive_title(report_type: str) -> str:
    return report_type.replace("_", " ").title()
