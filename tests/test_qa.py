from unittest.mock import patch

from app.schemas.query import ChatMessage
from app.services.qa import _derive_timeline_hint, _format_history, _humanize_answer_text, _wants_detailed_answer, answer_question


def test_answer_question_small_talk_skips_retrieval_and_model():
    fake_db = object()

    with patch("app.services.qa.retrieve_chunks") as mock_retrieve, patch("app.services.qa.genai.Client") as mock_client:
        response = answer_question(fake_db, "hello!!")

    assert response.sources == []
    assert "Ask me about my internship work" in response.answer
    mock_retrieve.assert_not_called()
    mock_client.assert_not_called()


def test_answer_question_returns_no_evidence_when_retrieval_empty():
    fake_db = object()

    with patch("app.services.qa.retrieve_chunks", return_value=[]), patch("app.services.qa.genai.Client") as mock_client:
        response = answer_question(fake_db, "What did I do?")

    assert response.answer == "I don't have enough evidence in the uploaded documents to answer that."
    assert response.sources == []
    mock_client.assert_not_called()


def test_humanize_answer_text_removes_internal_rag_wording():
    answer = _humanize_answer_text(
        "The retrieved context describes the author as an engineer working at the intersection of AI and Web3 (Internship_Report.pdf, Chunk 33)."
    )

    assert "retrieved context" not in answer.lower()
    assert "Chunk 33" not in answer
    assert answer == "the author as an engineer working at the intersection of AI and Web3."


def test_humanize_answer_text_removes_document_disclaimer():
    answer = _humanize_answer_text("Based on the documents, I have approximately 1 year of work experience.")

    assert "based on the documents" not in answer.lower()
    assert answer == "I have approximately 1 year of work experience."


def test_detailed_answer_detection():
    assert _wants_detailed_answer("Tell me more about your backend work")
    assert _wants_detailed_answer("Explain in detail what you worked on")
    assert not _wants_detailed_answer("What backend work did you do?")


def test_format_history_limits_to_recent_messages():
    history = [ChatMessage(role="user", content=f"q{i}") for i in range(8)]

    formatted = _format_history(history)

    assert "q0" not in formatted
    assert "q1" not in formatted
    assert "q7" in formatted


def test_derive_timeline_hint_from_retrieved_chunks():
    class ChunkLike:
        def __init__(self, chunk_text):
            self.chunk_text = chunk_text

    results = [
        (ChunkLike("Worked from 1 August 2025 to 26 September 2025."), object(), 0.1),
        (ChunkLike("Reporting Period: 1st January 2026 – 6th March 2026"), object(), 0.2),
    ]

    hint = _derive_timeline_hint(results)

    assert "01 August 2025" in hint
    assert "06 March 2026" in hint
    assert "approximate documented span" in hint


def test_derive_timeline_hint_from_resume_month_ranges():
    class ChunkLike:
        def __init__(self, chunk_text):
            self.chunk_text = chunk_text

    results = [
        (ChunkLike("AI/ML Engineer Apr 2025 - Aug 2025"), object(), 0.1),
        (ChunkLike("Blockchain & AI Engineer Aug 2025 - Present"), object(), 0.2),
    ]

    hint = _derive_timeline_hint(results)

    assert "01 April 2025" in hint
    assert "approximate documented span" in hint
