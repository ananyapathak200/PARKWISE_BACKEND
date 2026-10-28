"""
routers/reviews.py — matches receipt.js on the frontend:
  POST /bookings/{booking_id}/review
  GET  /parking-areas/{area_id}/reviews
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
import models
import schemas

router = APIRouter(tags=["reviews"])


@router.post("/bookings/{booking_id}/review", response_model=schemas.ReviewOut)
def create_review(
    booking_id: str,
    payload: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="This isn't your booking.")
    if booking.status != "completed":
        raise HTTPException(status_code=400, detail="You can only review a completed booking.")

    existing = db.query(models.Review).filter(models.Review.booking_id == booking_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="You've already reviewed this booking.")

    review = models.Review(
        booking_id=booking_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@router.get("/parking-areas/{area_id}/reviews", response_model=List[schemas.ReviewOut])
def get_reviews_for_listing(area_id: str, db: Session = Depends(get_db)):
    area = db.query(models.ParkingArea).filter(models.ParkingArea.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Listing not found.")

    reviews = (
        db.query(models.Review)
        .join(models.Booking, models.Review.booking_id == models.Booking.id)
        .join(models.ParkingSlot, models.Booking.slot_id == models.ParkingSlot.id)
        .filter(models.ParkingSlot.parking_area_id == area_id)
        .order_by(models.Review.created_at.desc())
        .all()
    )
    return reviews