"""
dependencies.py — reusable FastAPI dependencies:
  get_current_user   -> resolves the logged-in user from the JWT (401 if missing/invalid)
  get_optional_user  -> same, but returns None for visitors who aren't logged in
  require_role(...)  -> also enforces role (403 otherwise)

The role is always read from the DATABASE, never trusted from the token
or the browser, so changing localStorage can't make anyone an admin.
"""

from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from database import get_db
from auth import decode_access_token
import models

# tokenUrl is just for the /docs "Authorize" button — the actual login
# endpoint is POST /auth/login, which returns the token in its response body.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def _user_from_token(token: str, db: Session) -> Optional[models.User]:
    try:
        payload = decode_access_token(token)
    except jwt.InvalidTokenError:
        return None
    return db.query(models.User).filter(models.User.id == payload.get("sub")).first()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    user = _user_from_token(token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(
    token: Optional[str] = Depends(optional_oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    return _user_from_token(token, db) if token else None


def require_role(*allowed_roles: str):
    """
    Usage:
        @router.post("/parking-areas")
        def create_listing(user: models.User = Depends(require_role("owner"))):
            ...
    """
    def dependency(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to do this.",
            )
        return user
    return dependency
