import logging
import re
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from sqlalchemy.orm import Session

from app.config import get_settings
from app.schemas.query import AskResponse, ChatMessage, QueryFilters, SourceReference
from app.services.chat_intents import try_small_talk_response
from app.services.generation_errors import GenerationTemporarilyUnavailableError
from app.services.retrieval import retrieve_chunks


logger = logging.getLogger(__name__)
settings = get_settings()
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "qa_prompt.txt"
DETAIL_REQUEST_PATTERNS = (
    "tell me more",
    "more detail",
    "in detail",
    "elaborate",
    "explain more",
    "go deeper",
    "expand on",
    "detailed",
)
MAX_HISTORY_MESSAGES = 6
DATE_PATTERN = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})\b",
    re.IGNORECASE,
)
MONTH_NAME_PATTERN = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
MONTH_YEAR_PATTERN = re.compile(
    rf"\b({MONTH_NAME_PATTERN})\s+(\d{{4}})\b",
    re.IGNORECASE,
)
MONTH_YEAR_RANGE_PATTERN = re.compile(
    rf"\b({MONTH_NAME_PATTERN})\s+(\d{{4}})\s*[–—-]\s*"
    rf"({MONTH_NAME_PATTERN}|Present)\s*(\d{{4}})?\b",
    re.IGNORECASE,
)
EXPERIENCE_QUESTION_PATTERNS = (
    "work experience",
    "how much experience",
    "how many years",
    "how many months",
    "how long have",
    "experience do you have",
)


def _is_temporary_generation_error(exc: Exception) -> bool:
    message = str(exc).upper()
    return "503" in message or "UNAVAILABLE" in message or "HIGH DEMAND" in message


def _is_quota_generation_error(exc: Exception) -> bool:
    message = str(exc).upper()
    return "429" in message or "RESOURCE_EXHAUSTED" in message or "QUOTA" in message


def _humanize_answer_text(answer: str) -> str:
    cleaned = answer.strip()
    cleaned = re.sub(r"^\s*the retrieved context\s+(describes|shows|indicates|suggests)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^\s*(based on (?:the )?(?:documents|uploaded documents|uploaded reports|reports)|from (?:the )?(?:uploaded documents|uploaded reports|reports)),?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*\((?:[^()]*?(?:chunk|page|document id)[^()]*)\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?<!\n)[\u2022•]\s*", "\n- ", cleaned)
    cleaned = re.sub(r"\s+\*\s+", "\n- ", cleaned)
    cleaned = re.sub(r":\s+\*\s+", ":\n- ", cleaned)
    cleaned = re.sub(r"(?<!\n)-\s+\*\*(.*?)\*\*:", r"\n- \1:", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _wants_detailed_answer(question: str) -> bool:
    normalized = " ".join(question.lower().strip().split())
    return any(pattern in normalized for pattern in DETAIL_REQUEST_PATTERNS)


def _is_experience_question(question: str) -> bool:
    normalized = " ".join(question.lower().strip().split())
    return any(pattern in normalized for pattern in EXPERIENCE_QUESTION_PATTERNS)


def _trim_history(history: list[ChatMessage] | None) -> list[ChatMessage]:
    if not history:
        return []
    return history[-MAX_HISTORY_MESSAGES:]


def _format_history(history: list[ChatMessage] | None) -> str:
    trimmed = _trim_history(history)
    if not trimmed:
        return "No prior conversation."

    lines: list[str] = []
    for message in trimmed:
        role = "User" if message.role.lower() == "user" else "Assistant"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines)


def _extract_explicit_dates(text: str) -> list[datetime]:
    dates: list[datetime] = []
    for day, month, year in DATE_PATTERN.findall(text):
        try:
            dates.append(datetime.strptime(f"{int(day)} {month.title()} {year}", "%d %B %Y"))
        except ValueError:
            continue
    return dates


def _parse_month_year(month: str, year: str) -> datetime | None:
    try:
        return datetime.strptime(f"01 {month.title()} {year}", "%d %B %Y")
    except ValueError:
        try:
            return datetime.strptime(f"01 {month.title()} {year}", "%d %b %Y")
        except ValueError:
            return None


def _extract_month_year_dates(text: str) -> list[datetime]:
    dates: list[datetime] = []
    seen: set[tuple[str, str]] = set()
    for month, year in MONTH_YEAR_PATTERN.findall(text):
        key = (month.lower(), year)
        if key in seen:
            continue
        seen.add(key)
        parsed = _parse_month_year(month, year)
        if parsed is not None:
            dates.append(parsed)
    return dates


def _extract_month_year_range_dates(text: str) -> list[datetime]:
    dates: list[datetime] = []
    now = datetime.now()
    for start_month, start_year, end_month_or_present, end_year in MONTH_YEAR_RANGE_PATTERN.findall(text):
        start = _parse_month_year(start_month, start_year)
        if start is not None:
            dates.append(start)

        if end_month_or_present.lower() == "present":
            dates.append(now)
        elif end_year:
            end = _parse_month_year(end_month_or_present, end_year)
            if end is not None:
                dates.append(end)
    return dates


def _derive_timeline_hint(results: list[tuple[object, object, float]]) -> str:
    dates: list[datetime] = []
    for chunk, _doc, _distance in results:
        dates.extend(_extract_explicit_dates(chunk.chunk_text))
        dates.extend(_extract_month_year_range_dates(chunk.chunk_text))
        dates.extend(_extract_month_year_dates(chunk.chunk_text))

    if len(dates) < 2:
        return "No explicit timeline span could be derived from the retrieved context."

    earliest = min(dates)
    latest = max(dates)
    days = max((latest - earliest).days, 0)
    approx_months = max(round(days / 30.4), 0)

    return (
        "Derived timeline hint: earliest explicit date "
        f"{earliest.strftime('%d %B %Y')}; latest explicit date {latest.strftime('%d %B %Y')}; "
        f"approximate documented span {approx_months} months."
    )


def answer_question(
    db: Session,
    question: str,
    history: list[ChatMessage] | None = None,
    filters: QueryFilters | None = None,
    top_k: int | None = None,
) -> AskResponse:
    if not settings.gemini_api_key.strip():
        raise RuntimeError("GEMINI_API_KEY is missing.")

    small_talk = try_small_talk_response(question)
    if small_talk is not None:
        logger.info("Handled question as small talk without retrieval: %r", question)
        return small_talk

    results = retrieve_chunks(db, question, filters, top_k or settings.retrieval_top_k)

    if not results:
        logger.info("No grounded evidence found for question=%r", question)
        return AskResponse(
            answer="I don't have enough evidence in the uploaded documents to answer that.",
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

    context_blocks = []
    for chunk, doc, distance in results:
        context_blocks.append(
            "\n".join(
                [
                    f"Document: {doc.title}",
                    f"Document ID: {doc.id}",
                    f"Chunk Index: {chunk.chunk_index}",
                    f"Page Number: {chunk.page_number}",
                    f"Section Title: {chunk.section_title}",
                    f"Distance: {distance}",
                    f"Content: {chunk.chunk_text}",
                ]
            )
        )

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = prompt_template.format(
        question=question,
        history=_format_history(history),
        timeline_hint=_derive_timeline_hint(results) if _is_experience_question(question) else "No derived timeline hint needed.",
        context="\n\n---\n\n".join(context_blocks),
        response_mode="detailed" if _wants_detailed_answer(question) else "concise",
    )

    logger.info("Generating QA response with %s grounded chunks", len(results))

    try:
        response = client.models.generate_content(
            model=settings.gemini_chat_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                system_instruction=(
                    "Answer only from the retrieved context. "
                    "If the context is insufficient, say that clearly and do not invent facts."
                ),
            ),
        )
    except genai_errors.ServerError as exc:
        if _is_quota_generation_error(exc):
            logger.warning("Gemini generation quota exhausted")
            raise GenerationTemporarilyUnavailableError(
                "Question quota hit for Gemini right now. Wait a bit, or switch to paid quota / another model."
            ) from exc
        if getattr(exc, "status_code", None) == 503 or _is_temporary_generation_error(exc):
            logger.warning("Gemini generation temporarily unavailable")
            raise GenerationTemporarilyUnavailableError(
                "The answer model is temporarily busy. Please try the same question again in a minute."
            ) from exc
        logger.exception("QA generation failed")
        raise RuntimeError(f"QA generation failed: {exc}") from exc
    except Exception as exc:
        if _is_quota_generation_error(exc):
            logger.warning("Gemini generation quota exhausted")
            raise GenerationTemporarilyUnavailableError(
                "Question quota hit for Gemini right now. Wait a bit, or switch to paid quota / another model."
            ) from exc
        if _is_temporary_generation_error(exc):
            logger.warning("Gemini generation temporarily unavailable")
            raise GenerationTemporarilyUnavailableError(
                "The answer model is temporarily busy. Please try the same question again in a minute."
            ) from exc
        logger.exception("QA generation failed")
        raise RuntimeError(f"QA generation failed: {exc}") from exc

    answer = _humanize_answer_text((response.text or "").strip())
    return AskResponse(answer=answer, sources=sources)
