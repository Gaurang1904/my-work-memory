from app.config import get_settings
from app.services.auth import hash_password, verify_password


def test_password_hash_round_trip():
    password = "super-secret"
    password_hash = hash_password(password)

    settings = get_settings().model_copy(update={"admin_password_hash": password_hash, "admin_password": ""})

    assert verify_password(password, settings)
