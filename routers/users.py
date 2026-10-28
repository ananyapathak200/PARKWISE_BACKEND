"""
routers/users.py — matches js/auth.js on the frontend exactly:
  POST /auth/signup
  POST /auth/login
  GET  /auth/me
  POST /auth/forgot-password
  POST /auth/reset-password
"""

import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
import models
import schemas
import auth as auth_utils
from utils.email import send_password_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=schemas.TokenResponse)
def signup(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user = models.User(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        password_hash=auth_utils.hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = auth_utils.create_access_token(user.id, user.role)
    return schemas.TokenResponse(access_token=token, role=user.role)


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not auth_utils.verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    token = auth_utils.create_access_token(user.id, user.role)
    return schemas.TokenResponse(access_token=token, role=user.role)


@router.get("/me", response_model=schemas.UserOut)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    return current_user


RESET_TOKEN_EXPIRY_MINUTES = 30


@router.post("/forgot-password")
def forgot_password(
    payload: schemas.ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Always returns the same generic message, whether or not the email
    exists — otherwise this endpoint could be used to discover which
    emails are registered. The email itself is sent in the background
    so the response time doesn't leak that either.
    """
    generic_response = {
        "detail": "If an account with that email exists, a reset link has been sent."
    }

    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user:
        return generic_response

    token = secrets.token_urlsafe(32)
    user.reset_token = token
    user.reset_token_expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)
    db.commit()

    background_tasks.add_task(send_password_reset_email, user.email, token)
    return generic_response


@router.post("/reset-password")
def reset_password(payload: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.reset_token == payload.token).first()

    if (
        not user
        or user.reset_token_expires_at is None
        or user.reset_token_expires_at < datetime.utcnow()
    ):
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")

    user.password_hash = auth_utils.hash_password(payload.new_password)
    # Single-use: clear the token immediately so the same link can't be reused.
    user.reset_token = None
    user.reset_token_expires_at = None
    db.commit()

    return {"detail": "Password updated. You can now log in."}