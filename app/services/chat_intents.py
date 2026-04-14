import re

from app.schemas.query import AskResponse


WORK_PROMPT = "Ask me about my internship work, backend projects, AI systems, timelines, or reports."
GREETING_RESPONSE = f"Hi. {WORK_PROMPT}"
THANKS_RESPONSE = "You're welcome."
IDENTITY_RESPONSE = "I am a grounded work assistant built on top of uploaded internship reports and project documents."
HELP_RESPONSE = f"I can answer questions about your work, projects, timelines, achievements, and uploaded reports. {WORK_PROMPT}"

GREETING_TRIGGERS = {
    "hi",
    "hello",
    "hey",
    "yo",
    "hiya",
    "good morning",
    "good afternoon",
    "good evening",
}

THANKS_TRIGGERS = {
    "thanks",
    "thank you",
    "thanks bro",
    "thanks buddy",
    "thx",
}

IDENTITY_TRIGGERS = {
    "who are you",
    "what are you",
}

HELP_TRIGGERS = {
    "help",
    "what can you do",
    "how can you help",
}


def _normalize(question: str) -> str:
    question = question.lower().strip()
    question = re.sub(r"[^\w\s]", " ", question)
    return " ".join(question.split())


def try_small_talk_response(question: str) -> AskResponse | None:
    normalized = _normalize(question)
    if not normalized:
        return AskResponse(answer="Ask me about my work, projects, timelines, or reports.", sources=[])

    if normalized in GREETING_TRIGGERS:
        return AskResponse(answer=GREETING_RESPONSE, sources=[])

    if normalized in THANKS_TRIGGERS:
        return AskResponse(answer=THANKS_RESPONSE, sources=[])

    if normalized in IDENTITY_TRIGGERS:
        return AskResponse(answer=IDENTITY_RESPONSE, sources=[])

    if normalized in HELP_TRIGGERS:
        return AskResponse(answer=HELP_RESPONSE, sources=[])

    return None
