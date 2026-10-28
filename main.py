"""
ParkWise backend entrypoint.

Run with:
    uvicorn main:app --reload

Then visit http://127.0.0.1:8000/docs for the interactive API docs —
you can test every endpoint there before wiring up the frontend JS.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import Base, engine
import models  # noqa: F401 — imported so Base.metadata knows about all tables
from routers import users, parking_areas, bookings, admin, reviews

# Creates tables that don't exist yet. Fine for development; once you
# have real data, switch to a migration tool (Alembic) instead of this.
Base.metadata.create_all(bind=engine)

os.makedirs("uploads", exist_ok=True)

app = FastAPI(
    title="ParkWise API",
    description="Smart Parking Allocation & Management System",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5501",
        "http://localhost:5501",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],  # restrict this to your real frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serves uploaded listing photos at http://127.0.0.1:8000/uploads/<filename>
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(users.router)
app.include_router(parking_areas.router)
app.include_router(bookings.router)
app.include_router(admin.router)
app.include_router(reviews.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ParkWise API"}