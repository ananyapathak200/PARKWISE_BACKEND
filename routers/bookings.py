"""
routers/bookings.py — the most important file in the backend.
Matches booking.html, active-ticket.html, checkout.html, receipt.html:
  POST /bookings                 (with overlap prevention)
  POST /bookings/{id}/checkin
  POST /bookings/{id}/checkout        (creates a Razorpay order — does NOT mark paid)
  POST /bookings/{id}/verify-payment  (the only thing that marks a booking completed)
  GET  /bookings/mine
"""

from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from database import get_db
from dependencies import get_current_user, require_role
from utils.qr import generate_qr_token
from utils.payments import create_order, verify_payment_signature, RAZORPAY_KEY_ID
import models
import schemas

router = APIRouter(prefix="/bookings", tags=["bookings"])

GRACE_PERIOD_MINUTES = 15


def _slot_has_overlap(db: Session, slot_id: str, start_time: datetime, end_time: datetime) -> bool:
    """
    The single most important query in this project.
    Two time ranges overlap if: existing.start < new.end AND existing.end > new.start
    Only bookings that are still 'live' (not cancelled/completed) block a new one.
    """
    conflict = (
        db.query(models.Booking)
        .filter(
            models.Booking.slot_id == slot_id,
            models.Booking.status.in_(["reserved", "checked_in"]),
            models.Booking.start_time < end_time,
            models.Booking.end_time > start_time,
        )
        .first()
    )
    return conflict is not None


def _auto_cancel_expired(db: Session, slot_id: str):
    """
    Releases any 'reserved' booking on this slot whose start_time is more
    than GRACE_PERIOD_MINUTES in the past with no check-in. Called
    opportunistically before checking availability, so stale reservations
    don't block real bookings forever.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=GRACE_PERIOD_MINUTES)
    expired = (
        db.query(models.Booking)
        .filter(
            models.Booking.slot_id == slot_id,
            models.Booking.status == "reserved",
            models.Booking.start_time < cutoff,
        )
        .all()
    )
    for booking in expired:
        booking.status = "cancelled"
    if expired:
        db.commit()


@router.post("", response_model=schemas.BookingOut)
def create_booking(
    payload: schemas.BookingCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_role("driver")),
):
    slot = db.query(models.ParkingSlot).filter(models.ParkingSlot.id == payload.slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found.")

    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time.")

    _auto_cancel_expired(db, slot.id)

    if _slot_has_overlap(db, slot.id, payload.start_time, payload.end_time):
        raise HTTPException(
            status_code=409,
            detail="This slot is already booked for the selected time. Try a different window.",
        )

    booking = models.Booking(
        user_id=user.id,
        slot_id=slot.id,
        vehicle_number=payload.vehicle_number,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status="reserved",
        qr_code_token=generate_qr_token(),
    )
    slot.status = "reserved"

    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.post("/{booking_id}/checkin", response_model=schemas.BookingOut)
def check_in(
    booking_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="This isn't your booking.")
    if booking.status != "reserved":
        raise HTTPException(status_code=400, detail=f"Cannot check in — booking is '{booking.status}'.")

    booking.status = "checked_in"
    booking.actual_checkin_time = datetime.utcnow()
    booking.slot.status = "occupied"

    db.commit()
    db.refresh(booking)
    return booking


@router.post("/{booking_id}/checkout", response_model=schemas.CheckoutInitResponse)
def check_out(
    booking_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Calculates the bill and creates a Razorpay order for it. The
    booking is NOT marked completed here, and the slot is NOT freed
    here — both only happen once /verify-payment confirms the payment
    actually went through. This matches how a real barrier-gate lot
    works: you calculate the fee when the car leaves, but the
    transaction isn't final until payment clears.
    """
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="This isn't your booking.")
    if booking.status != "checked_in":
        raise HTTPException(status_code=400, detail=f"Cannot check out — booking is '{booking.status}'.")

    booking.actual_checkout_time = datetime.utcnow()
    duration_hours = (booking.actual_checkout_time - booking.actual_checkin_time).total_seconds() / 3600
    # Minimum 15 minutes billed, same grace logic as the auto-cancel window
    duration_hours = max(duration_hours, GRACE_PERIOD_MINUTES / 60)

    price_per_hour = booking.slot.parking_area.price_per_hour
    booking.amount = round(duration_hours * price_per_hour, 2)

    order = create_order(amount_rupees=booking.amount, receipt=booking.id)
    booking.razorpay_order_id = order["id"]
    booking.payment_status = "unpaid"

    db.commit()
    db.refresh(booking)

    return schemas.CheckoutInitResponse(
        booking_id=booking.id,
        amount=booking.amount,
        razorpay_order_id=order["id"],
        razorpay_key_id=RAZORPAY_KEY_ID,
    )


@router.post("/{booking_id}/verify-payment", response_model=schemas.BookingOut)
def verify_payment(
    booking_id: str,
    payload: schemas.PaymentVerifyRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    The only endpoint that's allowed to mark a booking 'completed' and
    free its slot. Never trust the frontend's own "payment succeeded"
    event — always re-verify the signature server-side, using the
    secret key, before treating money as actually received.
    """
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="This isn't your booking.")
    if booking.razorpay_order_id != payload.razorpay_order_id:
        raise HTTPException(status_code=400, detail="Order ID doesn't match this booking.")
    if booking.payment_status == "paid":
        # Already verified earlier (e.g. duplicate request) — return the
        # existing state instead of re-processing.
        return booking

    is_valid = verify_payment_signature(
        razorpay_order_id=payload.razorpay_order_id,
        razorpay_payment_id=payload.razorpay_payment_id,
        razorpay_signature=payload.razorpay_signature,
    )

    if not is_valid:
        booking.payment_status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail="Payment verification failed. Please try again.")

    booking.payment_status = "paid"
    booking.razorpay_payment_id = payload.razorpay_payment_id
    booking.status = "completed"
    booking.slot.status = "available"

    db.commit()
    db.refresh(booking)
    return booking


@router.get("/mine", response_model=List[schemas.BookingOut])
def my_bookings(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Booking)
        .filter(models.Booking.user_id == user.id)
        .order_by(models.Booking.created_at.desc())
        .all()
    )
