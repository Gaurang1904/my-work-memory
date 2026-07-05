import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.query import AskRequest, AskResponse
from app.services.agent import answer_with_agent
from app.services.generation_errors import GenerationTemporarilyUnavailableError


router = APIRouter(prefix="/ask", tags=["ask"])
logger = logging.getLogger(__name__)


@router.post("", response_model=AskResponse)
def ask_question(payload: AskRequest, db: Session = Depends(get_db)) -> AskResponse:
    """Answer a question via the LangGraph agent: the LLM chooses tools (semantic
    search + structured project/skill lookups) and returns a grounded, cited answer."""
    logger.info("Question received: question=%r session=%s", payload.question, payload.session_id)
    try:
        response = answer_with_agent(db, payload.question, payload.session_id)
        logger.info("Question answered with %s sources", len(response.sources))
        return response
    except HTTPException:
        raise
    except GenerationTemporarilyUnavailableError as exc:
        logger.warning("Question answering temporarily unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Question answering failed")
        raise HTTPException(status_code=500, detail=f"Question answering failed: {exc}") from exc
