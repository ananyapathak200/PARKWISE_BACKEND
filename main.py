"""
ParkWise backend entrypoint.

Development:
    uvicorn main:app --reload --port 9000
    then visit http://127.0.0.1:9000/docs for the interactive API docs.

Production (ENVIRONMENT=production in .env):
    gunicorn main:app -k uvicorn.workers.UvicornWorker -w 2 -b 127.0.0.1:9000
    behind Nginx with HTTPS. /docs is switched off there.
"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import CORS_ORIGINS, IS_PRODUCTION, UPLOAD_DIR
from database import Base, engine
import models  # noqa: F401 — imported so Base.metadata knows about all tables
from routers import users, parking_areas, bookings, admin, reviews, geocode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("parkwise")

# Creates tables that don't exist yet. Fine for now; once you have real
# data and need to change a table, switch to a migration tool (Alembic).
Base.metadata.create_all(bind=engine)

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(
    title="ParkWise API",
    description="Smart Parking Allocation & Management System",
    version="0.2.0",
    # The interactive API pages list every endpoint — useful in development,
    # a free map for attackers in production.
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,          # only your own site, from .env
    allow_credentials=False,             # we use Authorization headers, not cookies
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"  # photos are shown on the frontend domain
    if IS_PRODUCTION:
        # Tell browsers to use HTTPS only, for a year, on every subdomain.
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # FastAPI's default 422 echoes back what was typed — including
    # passwords. Return only which field is wrong and why.
    errors = [
        {"loc": [str(p) for p in err.get("loc", [])], "msg": err.get("msg", "Invalid value")}
        for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    # Full details go to the server log only; the visitor gets a plain message
    # with no stack trace, file paths or database errors.
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side. Please try again."},
    )


# Serves uploaded listing photos at /uploads/<filename>
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(users.router)
app.include_router(parking_areas.router)
app.include_router(bookings.router)
app.include_router(admin.router)
app.include_router(reviews.router)
app.include_router(geocode.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ParkWise API"}
