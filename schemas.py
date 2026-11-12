"""
Pydantic schemas — the request/response shapes the frontend's api.js
functions send and expect back. Keeping these separate from models.py
(the DB tables) is intentional: never expose password_hash, for example.

Every field a user can type has limits here (length, format, range), so
bad or oversized input is rejected with a 422 before it reaches the
database — whatever the browser-side form allowed.
"""

from datetime import datetime, timezone
from typing import Optional, Literal, Annotated
from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator

Role = Literal["driver", "owner", "admin"]
SignupRole = Literal["driver", "owner"]  # admins are created with create_admin.py, never by signup
ListingStatus = Literal["pending", "approved", "rejected"]
BookingStatus = Literal["reserved", "checked_in", "completed", "cancelled"]
VehicleType = Literal["car", "bike", "both"]

# Reusable text types: surrounding spaces stripped, length capped.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?[0-9][0-9 \-]{6,17}$")]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
ListingName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]
ClockTime = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Token = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=200)]
RazorpayId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


def _lower_email(value: str) -> str:
    return value.strip().lower()


# ---------- users / auth ----------

class UserCreate(BaseModel):
    name: Name
    email: EmailStr
    phone: Phone
    password: Password
    role: SignupRole

    _email = field_validator("email")(_lower_email)


class UserLogin(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]

    _email = field_validator("email")(_lower_email)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    _email = field_validator("email")(_lower_email)


class ResetPasswordRequest(BaseModel):
    token: Token
    new_password: Password


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
    name: ListingName
    address: Address
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    price_per_hour: float = Field(gt=0, le=10000)
    slots: int = Field(gt=0, le=200)
    vehicle_type: VehicleType = "car"
    opening_time: Optional[ClockTime] = None
    closing_time: Optional[ClockTime] = None


class ParkingAreaUpdate(BaseModel):
    name: Optional[ListingName] = None
    address: Optional[Address] = None
    # The edit form sends new coordinates when the address changes.
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    price_per_hour: Optional[float] = Field(default=None, gt=0, le=10000)
    vehicle_type: Optional[VehicleType] = None
    opening_time: Optional[ClockTime] = None
    closing_time: Optional[ClockTime] = None


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
    slot_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    # Indian plates like "UP65 AB 1234" — letters, digits, spaces and dashes.
    vehicle_number: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9 \-]{3,14}$")]
    start_time: datetime
    end_time: datetime

    @field_validator("start_time", "end_time")
    @classmethod
    def _to_utc_naive(cls, value: datetime) -> datetime:
        # The database stores UTC without a timezone; convert "…Z" / "+05:30" times to match.
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


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
    razorpay_order_id: RazorpayId
    razorpay_payment_id: RazorpayId
    razorpay_signature: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


# ---------- reviews ----------

class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]] = None
