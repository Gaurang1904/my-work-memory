from app.services.chat_intents import try_small_talk_response


def test_small_talk_hi_bypasses_rag():
    response = try_small_talk_response("hi")

    assert response is not None
    assert response.sources == []
    assert "Ask me about my internship work" in response.answer


def test_small_talk_with_punctuation_bypasses_rag():
    response = try_small_talk_response("hi!!")

    assert response is not None
    assert response.sources == []
    assert "Ask me about my internship work" in response.answer


def test_help_question_bypasses_rag():
    response = try_small_talk_response("what can you do?")

    assert response is not None
    assert response.sources == []
    assert "I can answer questions about your work" in response.answer
