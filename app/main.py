import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import check_db_connection, init_db
from app.routes.ask import router as ask_router
from app.routes.auth import router as auth_router
from app.routes.report import router as report_router
from app.routes.upload import router as upload_router
from app.services.auth import get_admin_session


settings = get_settings()
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"
PUBLIC_DIR = STATIC_DIR / "public"
ADMIN_DIR = STATIC_DIR / "admin"

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(upload_router)
app.include_router(ask_router)
app.include_router(report_router)
app.include_router(auth_router)


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
def index() -> FileResponse:
    return FileResponse(PUBLIC_DIR / "index.html")


@app.get("/admin", response_model=None)
def admin(request: Request):
    if get_admin_session(request) is None:
        return RedirectResponse(url="/admin/login", status_code=303)
    return FileResponse(ADMIN_DIR / "index.html")
