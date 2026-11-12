"""
routers/parking_areas.py — matches search.html, find-parking.html,
dashboard.html, and listing-edit.html on the frontend:
  POST   /parking-areas
  GET    /parking-areas               (public search, with optional lat/lng/max_price/vehicle_type)
  GET    /parking-areas/mine
  GET    /parking-areas/{id}
  GET    /parking-areas/{id}/slots
  PATCH  /parking-areas/{id}
  DELETE /parking-areas/{id}
  POST   /parking-areas/{id}/photo
"""

import logging
import os
import uuid
from typing import Optional, List, Literal
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from config import UPLOAD_DIR
from database import get_db
from dependencies import get_current_user, get_optional_user, require_role
from utils.scoring import haversine_km, compute_score
import models
import schemas

router = APIRouter(prefix="/parking-areas", tags=["parking-areas"])
log = logging.getLogger("parkwise.uploads")

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def _image_extension(data: bytes) -> Optional[str]:
    """
    Decide the file type from the file's own first bytes, not from the
    name or Content-Type the browser sends (both are easy to fake). This
    stops someone uploading a web page or script renamed to .png.
    """
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def can_see_listing(area: models.ParkingArea, user: Optional[models.User]) -> bool:
    """Approved listings are public; pending/rejected ones only for their owner and admins."""
    if area.status == "approved":
        return True
    return user is not None and (user.id == area.owner_id or user.role == "admin")


def _to_out(area: models.ParkingArea, db: Session, lat: Optional[float] = None, lng: Optional[float] = None) -> schemas.ParkingAreaOut:
    total_slots = len(area.slots)
    available_slots = sum(1 for s in area.slots if s.status == "available")
    available_slot = next((s for s in area.slots if s.status == "available"), None)
    first_available_slot_id = available_slot.id if available_slot else None

    distance_km = None
    score = None
    if lat is not None and lng is not None:
        distance_km = round(haversine_km(lat, lng, area.latitude, area.longitude), 1)
        score = compute_score(distance_km, area.price_per_hour, available_slots, total_slots)

    rating_row = (
        db.query(func.avg(models.Review.rating), func.count(models.Review.id))
        .join(models.Booking, models.Review.booking_id == models.Booking.id)
        .join(models.ParkingSlot, models.Booking.slot_id == models.ParkingSlot.id)
        .filter(models.ParkingSlot.parking_area_id == area.id)
        .first()
    )
    avg_rating = round(rating_row[0], 1) if rating_row and rating_row[0] is not None else None
    review_count = rating_row[1] if rating_row else 0

    return schemas.ParkingAreaOut(
        id=area.id,
        owner_id=area.owner_id,
        name=area.name,
        address=area.address,
        latitude=area.latitude,
        longitude=area.longitude,
        price_per_hour=area.price_per_hour,
        vehicle_type=area.vehicle_type,
        image_url=area.image_url,
        opening_time=area.opening_time,
        closing_time=area.closing_time,
        status=area.status,
        total_slots=total_slots,
        available_slots=available_slots,
        distance_km=distance_km,
        score=score,
        first_available_slot_id=first_available_slot_id,
        avg_rating=avg_rating,
        review_count=review_count,
    )


def _get_owned_area(db: Session, area_id: str, owner: models.User) -> models.ParkingArea:
    area = db.query(models.ParkingArea).filter(models.ParkingArea.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Listing not found.")
    if area.owner_id != owner.id:
        raise HTTPException(status_code=403, detail="You don't own this listing.")
    return area


@router.post("", response_model=schemas.ParkingAreaOut)
def create_listing(
    payload: schemas.ParkingAreaCreate,
    db: Session = Depends(get_db),
    owner: models.User = Depends(require_role("owner")),
):
    area = models.ParkingArea(
        owner_id=owner.id,
        name=payload.name,
        address=payload.address,
        latitude=payload.latitude,
        longitude=payload.longitude,
        price_per_hour=payload.price_per_hour,
        vehicle_type=payload.vehicle_type,
        opening_time=payload.opening_time,
        closing_time=payload.closing_time,
        status="pending",  # always pending — only an admin can approve
    )
    db.add(area)
    db.flush()  # get area.id before creating slots

    for slot_number in range(1, payload.slots + 1):
        db.add(models.ParkingSlot(
            parking_area_id=area.id,
            slot_number=slot_number,
            vehicle_type=payload.vehicle_type,
            status="available",
        ))

    db.commit()
    db.refresh(area)
    return _to_out(area, db)


@router.get("", response_model=List[schemas.ParkingAreaOut])
def search_listings(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lng: Optional[float] = Query(None, ge=-180, le=180),
    max_price: Optional[float] = Query(None, ge=0, le=100000),
    vehicle_type: Optional[Literal["car", "bike"]] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.ParkingArea).filter(models.ParkingArea.status == "approved")

    if max_price is not None:
        query = query.filter(models.ParkingArea.price_per_hour <= max_price)

    if vehicle_type is not None:
        # "both" listings match either filter; otherwise require an exact match
        query = query.filter(
            (models.ParkingArea.vehicle_type == vehicle_type) | (models.ParkingArea.vehicle_type == "both")
        )

    areas = query.all()
    results = [_to_out(a, db, lat, lng) for a in areas]

    if lat is not None and lng is not None:
        results.sort(key=lambda r: r.score, reverse=True)

    return results


@router.get("/mine", response_model=List[schemas.ParkingAreaOut])
def my_listings(
    db: Session = Depends(get_db),
    owner: models.User = Depends(require_role("owner")),
):
    areas = db.query(models.ParkingArea).filter(models.ParkingArea.owner_id == owner.id).all()
    return [_to_out(a, db) for a in areas]


@router.get("/mine/summary")
def my_listings_summary(db: Session = Depends(get_db), owner: models.User = Depends(require_role("owner"))):
    """
    Powers the owner dashboard's stats strip and recent-activity feed:
    live occupancy across every listing, today's revenue, and the last
    few bookings received — only for THIS owner's listings.
    """
    areas = db.query(models.ParkingArea).filter(models.ParkingArea.owner_id == owner.id).all()
    area_ids = [a.id for a in areas]

    total_slots = 0
    occupied_now = 0
    for a in areas:
        total_slots += len(a.slots)
        occupied_now += sum(1 for s in a.slots if s.status == "occupied")

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    bookings_today = (
        db.query(models.Booking)
        .join(models.ParkingSlot, models.Booking.slot_id == models.ParkingSlot.id)
        .filter(
            models.ParkingSlot.parking_area_id.in_(area_ids),
            models.Booking.status == "completed",
            models.Booking.actual_checkout_time >= today_start,
        )
        .all()
    )
    today_revenue = sum(b.amount or 0 for b in bookings_today)

    recent = (
        db.query(models.Booking)
        .join(models.ParkingSlot, models.Booking.slot_id == models.ParkingSlot.id)
        .filter(models.ParkingSlot.parking_area_id.in_(area_ids))
        .order_by(models.Booking.created_at.desc())
        .limit(6)
        .all()
    )
    recent_out = []
    for b in recent:
        area = b.slot.parking_area
        recent_out.append({
            "vehicle_number": b.vehicle_number,
            "listing_name": area.name,
            "status": b.status,
            "start_time": b.start_time.isoformat(),
            "amount": b.amount,
        })

    return {
        "total_listings": len(areas),
        "total_slots": total_slots,
        "occupied_now": occupied_now,
        "today_revenue": today_revenue,
        "recent_bookings": recent_out,
    }


@router.get("/{area_id}", response_model=schemas.ParkingAreaOut)
def get_listing(
    area_id: str,
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lng: Optional[float] = Query(None, ge=-180, le=180),
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(get_optional_user),
):
    area = db.query(models.ParkingArea).filter(models.ParkingArea.id == area_id).first()
    if not area or not can_see_listing(area, user):
        raise HTTPException(status_code=404, detail="Listing not found.")
    return _to_out(area, db, lat, lng)


@router.get("/{area_id}/slots", response_model=List[schemas.SlotOut])
def get_listing_slots(area_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    area = db.query(models.ParkingArea).filter(models.ParkingArea.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Listing not found.")
    if area.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="You don't own this listing.")
    slots = (
        db.query(models.ParkingSlot)
        .filter(models.ParkingSlot.parking_area_id == area_id)
        .order_by(models.ParkingSlot.slot_number)
        .all()
    )
    return slots


@router.patch("/{area_id}", response_model=schemas.ParkingAreaOut)
def update_listing(
    area_id: str,
    payload: schemas.ParkingAreaUpdate,
    db: Session = Depends(get_db),
    owner: models.User = Depends(require_role("owner")),
):
    area = _get_owned_area(db, area_id, owner)

    # Only the fields in ParkingAreaUpdate can change — never owner_id or
    # status, so an owner can't approve their own listing.
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(area, field, value)

    db.commit()
    db.refresh(area)
    return _to_out(area, db)


@router.post("/{area_id}/photo", response_model=schemas.ParkingAreaOut)
async def upload_listing_photo(
    area_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    owner: models.User = Depends(require_role("owner")),
):
    area = _get_owned_area(db, area_id, owner)

    contents = await file.read(MAX_IMAGE_SIZE_BYTES + 1)  # never read more than the limit
    if len(contents) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Image must be under 5 MB.")
    extension = _image_extension(contents)
    if extension is None:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, or WEBP images are allowed.")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = f"{uuid.uuid4()}.{extension}"  # our own name — the uploaded name is never used
    with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
        f.write(contents)

    old_url = area.image_url
    area.image_url = f"/uploads/{filename}"
    db.commit()
    db.refresh(area)
    _remove_upload(old_url)
    return _to_out(area, db)


def _remove_upload(image_url: Optional[str]) -> None:
    """Delete a replaced/orphaned photo so old files don't pile up."""
    if not image_url or not image_url.startswith("/uploads/"):
        return
    name = os.path.basename(image_url)
    path = os.path.join(UPLOAD_DIR, name)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        log.warning("Could not remove old upload %s", name)


@router.delete("/{area_id}")
def delete_listing(area_id: str, db: Session = Depends(get_db), owner: models.User = Depends(require_role("owner"))):
    area = _get_owned_area(db, area_id, owner)

    active_booking = (
        db.query(models.Booking)
        .join(models.ParkingSlot, models.Booking.slot_id == models.ParkingSlot.id)
        .filter(
            models.ParkingSlot.parking_area_id == area_id,
            models.Booking.status.in_(["reserved", "checked_in"]),
        )
        .first()
    )
    if active_booking:
        raise HTTPException(
            status_code=409,
            detail="Can't delete a listing with active bookings. Wait until they complete or cancel first.",
        )

    image_url = area.image_url
    db.delete(area)  # cascades to parking_slots too, since models.py sets cascade="all, delete-orphan"
    db.commit()
    _remove_upload(image_url)
    return {"detail": "Listing deleted."}
