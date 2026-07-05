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


def _make_chunk(index: int, text: str) -> Chunk:
    chunk = Chunk(document_id="00000000-0000-0000-0000-000000000000", chunk_index=index, chunk_text=text, embedding=[0.0])
    return chunk


def test_retrieve_chunks_dedupes_duplicate_text_across_duplicate_documents():
    doc_a = _make_doc("00000000-0000-0000-0000-000000000001", "Internship Report 2.pdf")
    doc_b = _make_doc("00000000-0000-0000-0000-000000000002", "Internship Report 2.pdf")
    shared_text = "Built backend APIs for reporting workflows."
    rows = [
        (_make_chunk(0, shared_text), doc_a, 0.11),
        (_make_chunk(0, shared_text), doc_b, 0.12),
    ]

    with patch("app.services.retrieval.EmbeddingService.embed_query", return_value=[0.1, 0.2]):
        results = retrieve_chunks(DummyDB(rows), "backend work", None, top_k=5)

    assert len(results) == 1
