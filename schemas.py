
"""
Pydantic schemas — the request/response shapes the frontend's api.js
functions send and expect back. Keeping these separate from models.py
(the DB tables) is intentional: never expose password_hash, for example.
"""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, EmailStr, Field

Role = Literal["driver", "owner", "admin"]
ListingStatus = Literal["pending", "approved", "rejected"]
BookingStatus = Literal["reserved", "checked_in", "completed", "cancelled"]


# ---------- users / auth ----------

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str
    password: str = Field(min_length=8)
    role: Role


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    phone: str
    role: Role

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role


# ---------- parking areas ----------

class ParkingAreaCreate(BaseModel):
    name: str
    address: str
    latitude: float
    longitude: float
    price_per_hour: float
    slots: int = Field(gt=0, le=200)
    vehicle_type: Literal["car", "bike", "both"] = "car"
    opening_time: Optional[str] = None
    closing_time: Optional[str] = None


class ParkingAreaUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    price_per_hour: Optional[float] = None
    vehicle_type: Optional[Literal["car", "bike", "both"]] = None
    opening_time: Optional[str] = None
    closing_time: Optional[str] = None


class ParkingAreaOut(BaseModel):
    id: str
    owner_id: str
    name: str
    address: str
    latitude: float
    longitude: float
    price_per_hour: float
    vehicle_type: str
    image_url: Optional[str] = None
    opening_time: Optional[str]
    closing_time: Optional[str]
    status: ListingStatus
    total_slots: int
    available_slots: int
    distance_km: Optional[float] = None
    score: Optional[int] = None
    first_available_slot_id: Optional[str] = None
    avg_rating: Optional[float] = None
    review_count: int = 0

    class Config:
        from_attributes = True


class ReviewOut(BaseModel):
    id: str 
    booking_id: str
    rating: int
    comment: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SlotOut(BaseModel):
    id: str
    slot_number: int
    status: str  # available | reserved | occupied

    class Config:
        from_attributes = True


# ---------- bookings ----------

class BookingCreate(BaseModel):
    slot_id: str
    vehicle_number: str
    start_time: datetime
    end_time: datetime


class BookingOut(BaseModel):
    id: str
    slot_id: str
    vehicle_number: str
    start_time: datetime
    end_time: datetime
    status: BookingStatus
    amount: Optional[float]
    payment_status: str
    razorpay_order_id: Optional[str] = None
    qr_code_token: str

    class Config:
        from_attributes = True


class CheckoutInitResponse(BaseModel):
    """
    Returned when checkout is initiated. The frontend uses this to open
    the Razorpay Checkout popup — note there's no key_secret here, only
    the public key_id, which is safe to expose to the browser.
    """
    booking_id: str
    amount: float
    razorpay_order_id: str
    razorpay_key_id: str
    currency: str = "INR"


class PaymentVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


# ---------- reviews ----------

class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None
