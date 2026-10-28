"""
dependencies.py — reusable FastAPI dependencies:
  get_current_user  -> resolves the logged-in user from the JWT
  require_role(...)  -> a dependency factory that also enforces role
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from database import get_db
from auth import decode_access_token
import models

# tokenUrl is just for the /docs "Authorize" button — the actual login
# endpoint is POST /auth/login, which returns the token in its response body.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_error
    except JWTError:
        raise credentials_error

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_error
    return user


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
                detail=f"This action requires one of these roles: {', '.join(allowed_roles)}",
            )
        return user
    return dependency
