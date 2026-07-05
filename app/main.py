import logging

from fastapi import FastAPI

from app.config import get_settings
from app.db import check_db_connection, init_db
from app.routes.ask import router as ask_router


settings = get_settings()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.include_router(ask_router)


@app.on_event("startup")
def on_startup() -> None:
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if not settings.database_url.strip():
        raise RuntimeError("DATABASE_URL is missing.")

    if not settings.gemini_api_key.strip():
        raise RuntimeError("GEMINI_API_KEY is missing.")

    check_db_connection()
    init_db()
    logger.info("Startup validation passed.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def index() -> dict[str, str]:
    return {"service": settings.app_name, "status": "ok", "docs": "/docs"}
