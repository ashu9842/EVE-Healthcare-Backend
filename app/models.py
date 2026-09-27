import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PaymentStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    is_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DiagnosticCentre(Base):
    __tablename__ = "diagnostic_centres"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), unique=True)
    location: Mapped[str] = mapped_column(String(255))
    tests: Mapped[list["DiagnosticTest"]] = relationship(back_populates="centre", cascade="all, delete-orphan")


class DiagnosticTest(Base):
    __tablename__ = "diagnostic_tests"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    price: Mapped[float] = mapped_column(Float)
    centre_id: Mapped[int] = mapped_column(ForeignKey("diagnostic_centres.id"), index=True)
    centre: Mapped[DiagnosticCentre] = relationship(back_populates="tests")


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    centre_id: Mapped[int] = mapped_column(ForeignKey("diagnostic_centres.id"))
    diagnostic_test_id: Mapped[int] = mapped_column(ForeignKey("diagnostic_tests.id"))
    appointment_at: Mapped[datetime] = mapped_column(DateTime)
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus), default=BookingStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped[User] = relationship()
    centre: Mapped[DiagnosticCentre] = relationship()
    diagnostic_test: Mapped[DiagnosticTest] = relationship()
    payments: Mapped[list["Payment"]] = relationship(back_populates="booking", cascade="all, delete-orphan")


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    provider_reference: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    booking: Mapped[Booking] = relationship(back_populates="payments")


class ProcessedWebhookEvent(Base):
    __tablename__ = "processed_webhook_events"
    __table_args__ = (UniqueConstraint("event_id", name="uq_webhook_event_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(100), unique=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
