from unittest.mock import patch

from app.services.report_generator import generate_report


def test_generate_report_returns_no_evidence_when_retrieval_empty():
    fake_db = object()

    with patch("app.services.report_generator.retrieve_chunks", return_value=[]), patch(
        "app.services.report_generator.genai.Client"
    ) as mock_client:
        response = generate_report(
            db=fake_db,
            report_type="final_internship_report",
            topic="Backend internship",
            filters=None,
        )

    assert response.title == "Final Internship Report"
    assert response.report == "I don't have enough evidence in the uploaded documents to generate this report."
    assert response.sources == []
    mock_client.assert_not_called()
