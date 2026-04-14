from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app


class DummyDB:
    def __init__(self) -> None:
        self.add_called = False
        self.flush_called = False
        self.commit_called = False
        self.rollback_called = False

    def add(self, obj) -> None:
        self.add_called = True

    def flush(self) -> None:
        self.flush_called = True

    def commit(self) -> None:
        self.commit_called = True

    def rollback(self) -> None:
        self.rollback_called = True

    def close(self) -> None:
        pass


def test_upload_rolls_back_when_embeddings_fail():
    db = DummyDB()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with patch("app.main.check_db_connection", return_value=None), patch(
        "app.main.init_db", return_value=None
    ), patch("app.routes.upload.detect_source_type", return_value="report"), patch(
        "app.routes.upload.extract_text",
        return_value=("Worked on APIs", [{"page_number": 1, "text": "Worked on APIs"}]),
    ), patch(
        "app.routes.upload.chunk_text",
        return_value=[
            {
                "chunk_index": 0,
                "chunk_text": "Worked on APIs",
                "page_number": 1,
                "section_title": None,
            }
        ],
    ), patch("app.routes.upload.EmbeddingService.embed_texts", side_effect=RuntimeError("embedding failure")):
        with TestClient(app) as client:
            response = client.post(
                "/upload",
                files={"file": ("sample.txt", BytesIO(b"Worked on APIs"), "text/plain")},
            )

    assert response.status_code == 500
    assert db.add_called is True
    assert db.flush_called is True
    assert db.commit_called is False
    assert db.rollback_called is True

    app.dependency_overrides.clear()
