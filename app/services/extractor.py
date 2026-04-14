from io import BytesIO
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader


def detect_source_type(filename: str, provided_source_type: str | None = None) -> str:
    if provided_source_type:
        return provided_source_type
    extension = Path(filename).suffix.lower()
    mapping = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".txt": "txt",
        ".md": "md",
    }
    return mapping.get(extension, "note")


def extract_text(file_bytes: bytes, filename: str) -> tuple[str, list[dict]]:
    extension = Path(filename).suffix.lower()

    if extension == ".pdf":
        return _extract_pdf(file_bytes)
    if extension == ".docx":
        return _extract_docx(file_bytes)
    if extension in {".txt", ".md"}:
        return _extract_textlike(file_bytes)

    raise ValueError(f"Unsupported file type: {extension}")


def _extract_pdf(file_bytes: bytes) -> tuple[str, list[dict]]:
    reader = PdfReader(BytesIO(file_bytes))
    pages: list[dict] = []

    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append({"page_number": index, "text": text})

    combined = "\n\n".join(page["text"] for page in pages)
    return combined, pages


def _extract_docx(file_bytes: bytes) -> tuple[str, list[dict]]:
    document = DocxDocument(BytesIO(file_bytes))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    text = "\n".join(paragraphs)
    return text, [{"page_number": None, "text": text}] if text else []


def _extract_textlike(file_bytes: bytes) -> tuple[str, list[dict]]:
    text = file_bytes.decode("utf-8", errors="ignore").strip()
    return text, [{"page_number": None, "text": text}] if text else []

