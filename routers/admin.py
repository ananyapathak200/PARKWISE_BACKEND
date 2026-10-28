"""
routers/admin.py — matches admin.html:
  GET   /admin/pending-listings
  PATCH /admin/parking-areas/{id}/approve
  PATCH /admin/parking-areas/{id}/reject
  GET   /admin/stats
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_role
import models
import schemas

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/pending-listings", response_model=List[schemas.ParkingAreaOut])
def pending_listings(db: Session = Depends(get_db), admin: models.User = Depends(require_role("admin"))):
    from routers.parking_areas import _to_out
    areas = db.query(models.ParkingArea).filter(models.ParkingArea.status == "pending").all()
    return [_to_out(a, db) for a in areas]


@router.patch("/parking-areas/{area_id}/approve", response_model=schemas.ParkingAreaOut)
def approve_listing(area_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_role("admin"))):
    from routers.parking_areas import _to_out

    area = db.query(models.ParkingArea).filter(models.ParkingArea.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Listing not found.")
    area.status = "approved"
    db.commit()
    db.refresh(area)
    return _to_out(area, db)


@router.patch("/parking-areas/{area_id}/reject", response_model=schemas.ParkingAreaOut)
def reject_listing(area_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_role("admin"))):
    from routers.parking_areas import _to_out

    area = db.query(models.ParkingArea).filter(models.ParkingArea.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Listing not found.")
    area.status = "rejected"
    db.commit()
    db.refresh(area)
    return _to_out(area, db)


@router.get("/stats")
def admin_stats(db: Session = Depends(get_db), admin: models.User = Depends(require_role("admin"))):
    total_listings = db.query(models.ParkingArea).count()
    approved = db.query(models.ParkingArea).filter(models.ParkingArea.status == "approved").count()
    active_bookings = (
        db.query(models.Booking)
        .filter(models.Booking.status.in_(["reserved", "checked_in"]))
        .count()
    )
    revenue = (
        db.query(models.Booking)
        .filter(models.Booking.status == "completed")
        .all()
    )
    total_revenue = sum(b.amount or 0 for b in revenue)

    return {
        "total_listings": total_listings,
        "approved": approved,
        "active_bookings": active_bookings,
        "revenue": total_revenue,
    }