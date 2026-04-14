from sqlalchemy.orm import Session

from app.models.chunk import Chunk


def add_chunks(db: Session, chunks: list[Chunk]) -> None:
    db.add_all(chunks)
    db.flush()

