from fastapi.testclient import TestClient
from unittest.mock import patch

from app.config import get_settings
from app.main import app
from app.services.auth import create_session_token, hash_password, verify_password


def test_password_hash_round_trip():
    password = "super-secret"
    password_hash = hash_password(password)

    settings = get_settings().model_copy(update={"admin_password_hash": password_hash, "admin_password": ""})

    assert verify_password(password, settings)


def test_admin_page_redirects_when_logged_out():
    with patch("app.main.check_db_connection", return_value=None), patch("app.main.init_db", return_value=None):
        with TestClient(app) as client:
            response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_page_loads_when_logged_in():
    settings = get_settings()
    token = create_session_token(settings.admin_username, settings)

    with patch("app.main.check_db_connection", return_value=None), patch("app.main.init_db", return_value=None):
        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, token)
            response = client.get("/admin")

    assert response.status_code == 200
    assert "Admin Ingest Console" in response.text
