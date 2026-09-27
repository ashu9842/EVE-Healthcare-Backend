from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import BookingStatus, PaymentStatus


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    price: float


class CentreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    location: str
    tests: list[TestOut]


class CentreIn(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    location: str = Field(min_length=2, max_length=255)


class TestIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    price: float = Field(gt=0, le=100000)


class BookingIn(BaseModel):
    centre_id: int = Field(gt=0)
    diagnostic_test_id: int = Field(gt=0)
    appointment_at: datetime


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    centre_id: int
    diagnostic_test_id: int
    appointment_at: datetime
    amount: float
    status: BookingStatus


class PaymentIn(BaseModel):
    booking_id: int = Field(gt=0)
    # Explicit only for deterministic integration testing of the simulator.
    simulate_status: PaymentStatus | None = None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    booking_id: int
    provider_reference: str
    amount: float
    status: PaymentStatus


class WebhookIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    booking_id: int = Field(gt=0)
    provider_reference: str = Field(min_length=1, max_length=100)
    status: PaymentStatus
    amount: float = Field(gt=0)
