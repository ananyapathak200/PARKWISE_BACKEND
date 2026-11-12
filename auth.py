"""
auth.py — password hashing, reset-token hashing and JWT creation/verification.

Uses PyJWT (actively maintained) instead of python-jose, which pulled in
the `ecdsa` package with a known, unfixed timing weakness.
"""

import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES


def hash_password(plain_password: str) -> str:
    # bcrypt only uses the first 72 bytes of a password — a hard limit of
    # the algorithm. The signup form caps passwords at 128 characters.
    pwd_bytes = plain_password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    pwd_bytes = plain_password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(pwd_bytes, password_hash.encode("utf-8"))
    except ValueError:  # malformed hash in the database
        return False


# A real bcrypt hash used when the email doesn't exist, so a failed login
# takes the same time either way and can't reveal which emails are registered.
_DUMMY_HASH = hash_password("parkwise-timing-equaliser")


def burn_password_check(plain_password: str) -> None:
    verify_password(plain_password, _DUMMY_HASH)


def hash_reset_token(token: str) -> str:
    """
    Reset links are stored only as a SHA-256 hash, like passwords: anyone
    who reads the database can't use a pending reset link.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.InvalidTokenError for anything expired, forged or malformed."""
    payload = jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
    if payload.get("type", "access") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload
