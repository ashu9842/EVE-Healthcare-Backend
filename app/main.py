import os
import secrets
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .database import Base, engine, get_db
from .cache import delete as cache_delete, get_json, set_json
from .models import Booking, BookingStatus, DiagnosticCentre, DiagnosticTest, Payment, PaymentStatus, ProcessedWebhookEvent, User
from .schemas import (BookingIn, BookingOut, CentreIn, CentreOut, LoginIn, PaymentIn, PaymentOut,
                      SignupIn, TestIn, TestOut, TokenOut, WebhookIn)
from .security import create_access_token, get_current_user, hash_password, require_admin, verify_password
from .tasks import queue_payment_notification

app = FastAPI(title="EVE Healthcare Booking API", version="1.0.0")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "local-webhook-secret")


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        admin_email = os.getenv("ADMIN_EMAIL")
        admin_password = os.getenv("ADMIN_PASSWORD")
        if admin_email and admin_password and not db.scalar(select(User).where(User.email == admin_email.lower())):
            db.add(User(email=admin_email.lower(), full_name="EVE Administrator", password_hash=hash_password(admin_password), is_admin=True))
        if not db.scalar(select(DiagnosticCentre.id).limit(1)):
            centre = DiagnosticCentre(name="EVE Diagnostics — Indiranagar", location="100 Feet Road, Bengaluru")
            centre.tests = [DiagnosticTest(name="Complete Blood Count", price=450), DiagnosticTest(name="Thyroid Profile", price=850)]
            db.add(centre)
        db.commit()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/signup", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(email=payload.email.lower(), full_name=payload.full_name, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_access_token(user.id))


@app.post("/auth/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return TokenOut(access_token=create_access_token(user.id))


@app.get("/centres", response_model=list[CentreOut])
def list_centres(db: Session = Depends(get_db)):
    cached = get_json("catalogue:centres")
    if cached is not None:
        return cached
    centres = db.scalars(select(DiagnosticCentre).options(selectinload(DiagnosticCentre.tests))).all()
    serialized = [CentreOut.model_validate(centre).model_dump() for centre in centres]
    set_json("catalogue:centres", serialized)
    return centres


@app.get("/centres/{centre_id}", response_model=CentreOut)
def get_centre(centre_id: int, db: Session = Depends(get_db)):
    centre = db.scalar(select(DiagnosticCentre).where(DiagnosticCentre.id == centre_id).options(selectinload(DiagnosticCentre.tests)))
    if not centre:
        raise HTTPException(status_code=404, detail="Centre not found")
    return centre


@app.post("/centres", response_model=CentreOut, status_code=201)
def create_centre(payload: CentreIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    centre = DiagnosticCentre(**payload.model_dump())
    db.add(centre)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Centre name already exists")
    db.refresh(centre)
    cache_delete("catalogue:centres")
    return centre


@app.post("/centres/{centre_id}/tests", response_model=TestOut, status_code=201)
def create_test(centre_id: int, payload: TestIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not db.get(DiagnosticCentre, centre_id):
        raise HTTPException(status_code=404, detail="Centre not found")
    test = DiagnosticTest(centre_id=centre_id, **payload.model_dump())
    db.add(test)
    db.commit()
    db.refresh(test)
    cache_delete("catalogue:centres")
    return test


@app.post("/bookings", response_model=BookingOut, status_code=201)
def create_booking(payload: BookingIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.appointment_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="appointment_at must include a timezone")
    if payload.appointment_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Appointment must be in the future")
    test = db.get(DiagnosticTest, payload.diagnostic_test_id)
    if not test or test.centre_id != payload.centre_id:
        raise HTTPException(status_code=422, detail="Test is not offered by this centre")
    booking = Booking(user_id=user.id, centre_id=payload.centre_id, diagnostic_test_id=test.id,
                      appointment_at=payload.appointment_at, amount=test.price, status=BookingStatus.PENDING)
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@app.get("/bookings", response_model=list[BookingOut])
def list_bookings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(Booking).where(Booking.user_id == user.id).order_by(Booking.appointment_at)).all()


@app.post("/bookings/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="You do not own this booking")
    if booking.status != BookingStatus.PENDING:
        raise HTTPException(status_code=409, detail="Only pending bookings can be cancelled")
    booking.status = BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)
    return booking


def apply_payment(db: Session, booking: Booking, provider_reference: str, outcome: PaymentStatus, amount: float) -> Payment:
    payment = Payment(booking_id=booking.id, provider_reference=provider_reference, amount=amount, status=outcome)
    booking.status = BookingStatus.CONFIRMED if outcome == PaymentStatus.SUCCESS else BookingStatus.FAILED
    db.add(payment)
    return payment


@app.post("/payments", response_model=PaymentOut, status_code=201)
def process_payment(payload: PaymentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    booking = db.get(Booking, payload.booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="You do not own this booking")
    if booking.status != BookingStatus.PENDING:
        raise HTTPException(status_code=409, detail="Booking is not awaiting payment")
    outcome = payload.simulate_status or (PaymentStatus.SUCCESS if secrets.randbelow(100) < 80 else PaymentStatus.FAILED)
    payment = apply_payment(db, booking, f"sim_{secrets.token_urlsafe(12)}", outcome, booking.amount)
    db.commit()
    db.refresh(payment)
    queue_payment_notification(booking.id, outcome.value)
    return payment


@app.post("/payments/webhook", response_model=PaymentOut)
def payment_webhook(payload: WebhookIn, x_webhook_secret: str | None = Header(default=None), db: Session = Depends(get_db)):
    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    # The unique event row is inserted in the same transaction as the payment/status update.
    # A duplicate delivery simply returns the original payment without touching the booking again.
    prior_event = db.scalar(select(ProcessedWebhookEvent).where(ProcessedWebhookEvent.event_id == payload.event_id))
    if prior_event:
        existing = db.scalar(select(Payment).where(Payment.provider_reference == payload.provider_reference))
        if not existing:
            raise HTTPException(status_code=409, detail="Duplicate event has no payment record")
        return existing
    booking = db.get(Booking, payload.booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status != BookingStatus.PENDING:
        raise HTTPException(status_code=409, detail="Booking is not awaiting payment")
    if abs(booking.amount - payload.amount) > 0.001:
        raise HTTPException(status_code=422, detail="Payment amount does not match booking")
    db.add(ProcessedWebhookEvent(event_id=payload.event_id))
    payment = apply_payment(db, booking, payload.provider_reference, payload.status, payload.amount)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Covers races where another delivery won after the first duplicate check.
        existing = db.scalar(select(Payment).where(Payment.provider_reference == payload.provider_reference))
        if existing:
            return existing
        raise HTTPException(status_code=409, detail="Conflicting payment event")
    db.refresh(payment)
    queue_payment_notification(booking.id, payload.status.value)
    return payment
