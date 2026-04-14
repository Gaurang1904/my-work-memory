from datetime import date

from pydantic import BaseModel, Field


class QueryFilters(BaseModel):
    project_name: str | None = None
    company_name: str | None = None
    source_type: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    tags: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str
    history: list[ChatMessage] = Field(default_factory=list)
    filters: QueryFilters | None = None
    top_k: int | None = None


class SourceReference(BaseModel):
    document: str
    document_id: str
    chunk_index: int
    page_number: int | None = None
    section_title: str | None = None
    excerpt: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
