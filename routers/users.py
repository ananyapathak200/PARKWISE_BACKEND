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
from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
import models
import schemas
import auth as auth_utils
from utils.email import send_password_reset_email
from utils.rate_limit import (
    client_ip,
    forgot_by_email,
    forgot_by_ip,
    login_attempts_by_ip,
    login_failures_by_email,
    reset_by_ip,
    signup_by_ip,
)

router = APIRouter(prefix="/auth", tags=["auth"])

RESET_TOKEN_EXPIRY_MINUTES = 30


def _find_user_by_email(db: Session, email: str):
    # Case-insensitive, so "Priya@Example.com" and "priya@example.com" are one account.
    return db.query(models.User).filter(func.lower(models.User.email) == email.lower()).first()


@router.post("/signup", response_model=schemas.TokenResponse)
def signup(payload: schemas.UserCreate, request: Request, db: Session = Depends(get_db)):
    signup_by_ip.hit(client_ip(request))

    if _find_user_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user = models.User(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        password_hash=auth_utils.hash_password(payload.password),
        role=payload.role,  # only "driver" or "owner" — the schema rejects "admin"
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = auth_utils.create_access_token(user.id, user.role)
    return schemas.TokenResponse(access_token=token, role=user.role)


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.UserLogin, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    login_attempts_by_ip.hit(ip)
    login_failures_by_email.check(payload.email)

    user = _find_user_by_email(db, payload.email)
    if not user:
        auth_utils.burn_password_check(payload.password)  # same timing as a wrong password
    if not user or not auth_utils.verify_password(payload.password, user.password_hash):
        login_failures_by_email.record(payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    login_failures_by_email.reset(payload.email)
    token = auth_utils.create_access_token(user.id, user.role)
    return schemas.TokenResponse(access_token=token, role=user.role)


@router.get("/me", response_model=schemas.UserOut)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/forgot-password")
def forgot_password(
    payload: schemas.ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Always returns the same generic message, whether or not the email
    exists — otherwise this endpoint could be used to discover which
    emails are registered. The email itself is sent in the background
    so the response time doesn't leak that either.
    """
    forgot_by_ip.hit(client_ip(request))
    generic_response = {
        "detail": "If an account with that email exists, a reset link has been sent."
    }

    # Too many reset emails to one address: quietly send nothing more,
    # so nobody can flood someone's inbox.
    if forgot_by_email.blocked(payload.email):
        return generic_response
    forgot_by_email.record(payload.email)

    user = _find_user_by_email(db, payload.email)
    if not user:
        return generic_response

    token = secrets.token_urlsafe(32)
    user.reset_token = auth_utils.hash_reset_token(token)  # only the hash is stored
    user.reset_token_expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)
    db.commit()

    background_tasks.add_task(send_password_reset_email, user.email, token)
    return generic_response


@router.post("/reset-password")
def reset_password(payload: schemas.ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    reset_by_ip.hit(client_ip(request))

    token_hash = auth_utils.hash_reset_token(payload.token)
    user = db.query(models.User).filter(models.User.reset_token == token_hash).first()

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
