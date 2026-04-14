from datetime import date

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    document_id: str
    title: str
    source_type: str
    chunks_created: int


class UploadMetadata(BaseModel):
    title: str | None = None
    source_type: str | None = None
    project_name: str | None = None
    company_name: str | None = None
    document_date: date | None = None
    tags: list[str] = Field(default_factory=list)


class RepoFileInfo(BaseModel):
    file_name: str
    relative_path: str
    size_bytes: int
    source_type: str


class LocalIngestRequest(BaseModel):
    file_name: str
    title: str | None = None
    source_type: str | None = None
    project_name: str | None = None
    company_name: str | None = None
    document_date: date | None = None
    tags: list[str] = Field(default_factory=list)
