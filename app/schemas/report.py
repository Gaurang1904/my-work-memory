from pydantic import BaseModel

from app.schemas.query import QueryFilters, SourceReference


class ReportRequest(BaseModel):
    report_type: str
    topic: str
    filters: QueryFilters | None = None


class ReportResponse(BaseModel):
    title: str
    report: str
    sources: list[SourceReference]

