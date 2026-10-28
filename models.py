
"""
ORM models. Status fields are plain strings (not native DB enums) so
this works identically on SQLite (local testing) and PostgreSQL
(production) without migration headaches — validity is enforced by the
Pydantic schemas in schemas.py before anything hits the database.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    ForeignKey,
    DateTime,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base


def generate_id():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    role = Column(String, nullable=False)  # driver | owner | admin
    created_at = Column(DateTime, default=datetime.utcnow)

    # Password reset fields
    reset_token = Column(String, nullable=True, index=True)
    reset_token_expires_at = Column(DateTime, nullable=True)

    parking_areas = relationship("ParkingArea", back_populates="owner")
    bookings = relationship("Booking", back_populates="user")


class ParkingArea(Base):
    __tablename__ = "parking_areas"

    id = Column(String, primary_key=True, default=generate_id)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    price_per_hour = Column(Float, nullable=False)
    vehicle_type = Column(String, nullable=False, default="car")
    image_url = Column(String, nullable=True)
    opening_time = Column(String, nullable=True)
    closing_time = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="parking_areas")
    slots = relationship(
        "ParkingSlot",
        back_populates="parking_area",
        cascade="all, delete-orphan",
    )


class ParkingSlot(Base):
    __tablename__ = "parking_slots"

    id = Column(String, primary_key=True, default=generate_id)
    parking_area_id = Column(
        String,
        ForeignKey("parking_areas.id"),
        nullable=False,
    )
    slot_number = Column(Integer, nullable=False)
    vehicle_type = Column(String, default="car")
    status = Column(String, nullable=False, default="available")

    parking_area = relationship("ParkingArea", back_populates="slots")
    bookings = relationship("Booking", back_populates="slot")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    slot_id = Column(
        String,
        ForeignKey("parking_slots.id"),
        nullable=False,
    )
    vehicle_number = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    actual_checkin_time = Column(DateTime, nullable=True)
    actual_checkout_time = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="reserved")
    amount = Column(Float, nullable=True)
    payment_status = Column(String, nullable=False, default="unpaid")
    razorpay_order_id = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)
    qr_code_token = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="bookings")
    slot = relationship("ParkingSlot", back_populates="bookings")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(String, primary_key=True, default=generate_id)
    booking_id = Column(String, ForeignKey("bookings.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
