from unittest.mock import patch

from app.models.chunk import Chunk
from app.models.document import Document
from app.services.retrieval import retrieve_chunks


class DummyResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class DummyDB:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _stmt):
        return DummyResult(self.rows)


def _make_doc(doc_id: str, title: str) -> Document:
    doc = Document(title=title, source_type="pdf", raw_text="x")
    doc.id = doc_id
    return doc


def _make_chunk(index: int, text: str, page_number: int) -> Chunk:
    chunk = Chunk(
        document_id="00000000-0000-0000-0000-000000000000",
        chunk_index=index,
        chunk_text=text,
        page_number=page_number,
        embedding=[0.0],
    )
    return chunk


def test_temporal_query_prefers_ongoing_work_chunk():
    doc = _make_doc("00000000-0000-0000-0000-000000000001", "Internship_Report.pdf")
    rows = [
        (
            _make_chunk(0, "Built backend APIs for reporting workflows.", 3),
            doc,
            0.18,
        ),
        (
            _make_chunk(1, "Remaining work includes oracle development and ongoing integration tasks.", 17),
            doc,
            0.22,
        ),
    ]

    with patch("app.services.retrieval.EmbeddingService.embed_query", return_value=[0.1, 0.2]):
        results = retrieve_chunks(DummyDB(rows), "What was I working on most recently?", None, top_k=1)

    assert len(results) == 1
    assert "Remaining work" in results[0][0].chunk_text
