import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Skill(Base):
    """A structured skill with evidence pointing back to projects.

    Enables honest coverage answers: "Does he know Deep Learning?" is resolved
    by looking here, so an absent skill returns a confident "no evidence"
    instead of a semantic near-miss.
    """

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    proficiency: Mapped[str | None] = mapped_column(String(40), nullable=True)
    related_project_slugs: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
