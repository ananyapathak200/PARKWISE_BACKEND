"""
config.py — the ONE place settings are read from.

Every secret (database password, JWT key, Razorpay secret, email
password) comes from environment variables — in development from the
.env file next to this one, in production from the server's own .env or
systemd EnvironmentFile. Nothing secret is ever written in the code, and
.env is listed in .gitignore so it can't reach GitHub.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)

log = logging.getLogger("parkwise.config")


def _get(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip()


def _required(name: str) -> str:
    value = _get(name)
    if not value:
        raise RuntimeError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


# "development" (default) or "production". Production turns off the
# /docs pages, turns on HSTS and refuses weak secrets.
ENVIRONMENT = _get("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# ---------- database ----------
DATABASE_URL = _required("DATABASE_URL")

# ---------- login tokens ----------
JWT_SECRET_KEY = _required("JWT_SECRET_KEY")
JWT_ALGORITHM = _get("JWT_ALGORITHM", "HS256")
if JWT_ALGORITHM not in {"HS256", "HS384", "HS512"}:
    raise RuntimeError("JWT_ALGORITHM must be HS256, HS384 or HS512.")
ACCESS_TOKEN_EXPIRE_MINUTES = int(_get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

_WEAK_SECRETS = {"secret", "changeme", "change-me", "dev-only-secret-change-me", "test-secret", "your-secret-key"}
if len(JWT_SECRET_KEY) < 32 or JWT_SECRET_KEY.lower() in _WEAK_SECRETS:
    message = (
        "JWT_SECRET_KEY is too weak. Generate one with:  "
        "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )
    if IS_PRODUCTION:
        raise RuntimeError(message)
    log.warning(message)

# ---------- payments ----------
RAZORPAY_KEY_ID = _required("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = _required("RAZORPAY_KEY_SECRET")

# ---------- email ----------
SMTP_EMAIL = _get("SMTP_EMAIL")
SMTP_APP_PASSWORD = _get("SMTP_APP_PASSWORD").replace(" ", "")
FRONTEND_RESET_URL = _get(
    "FRONTEND_RESET_URL", "http://127.0.0.1:5500/reset-password.html"
).rstrip("?&")

# ---------- browser access (CORS) ----------
# Comma-separated list of the exact sites allowed to call this API.
_DEV_ORIGINS = "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:5501,http://localhost:5501"
CORS_ORIGINS = [o.strip().rstrip("/") for o in _get("CORS_ORIGINS", "" if IS_PRODUCTION else _DEV_ORIGINS).split(",") if o.strip()]
if IS_PRODUCTION and (not CORS_ORIGINS or "*" in CORS_ORIGINS):
    raise RuntimeError("Set CORS_ORIGINS to your real site, e.g. https://parkwise.in,https://www.parkwise.in")

# ---------- uploads ----------
UPLOAD_DIR = _get("UPLOAD_DIR", str(BASE_DIR / "uploads"))
