import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.report import ReportRequest, ReportResponse
from app.services.generation_errors import GenerationTemporarilyUnavailableError
from app.services.report_generator import generate_report


router = APIRouter(prefix="/generate-report", tags=["report"])
logger = logging.getLogger(__name__)


@router.post("", response_model=ReportResponse)
def build_report(payload: ReportRequest, db: Session = Depends(get_db)) -> ReportResponse:
    try:
        response = generate_report(db, payload.report_type, payload.topic, payload.filters)
        logger.info("Report generated with %s sources", len(response.sources))
        return response
    except HTTPException:
        raise
    except GenerationTemporarilyUnavailableError as exc:
        logger.warning("Report generation temporarily unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Report generation failed")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}") from exc
