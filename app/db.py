from collections.abc import Generator

from pgvector.sqlalchemy import Vector
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


settings = get_settings()


class Base(DeclarativeBase):
    type_annotation_map = {list[float]: Vector(settings.embedding_dimensions)}


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def init_db() -> None:
    # Imported for its side effect: registers all ORM models on Base.metadata
    # so create_all() sees every table. Deferred to avoid a circular import.
    import app.models  # noqa: F401

    # pgvector must exist before create_all builds the Vector columns. Locally
    # docker-entrypoint runs sql/init.sql; on a managed host nothing does, so
    # create it here (idempotent, no superuser needed on supported hosts).
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(bind=engine)
