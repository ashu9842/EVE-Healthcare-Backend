import os
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "sqlite:///./test_eve.db"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["WEBHOOK_SECRET"] = "test-webhook-secret"

from fastapi.testclient import TestClient
from app.database import Base, engine
from app.main import app


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app):
        pass


def auth(client):
    response = client.post("/auth/signup", json={"email": "ada@example.com", "password": "safe-password", "full_name": "Ada Lovelace"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_booking_and_idempotent_webhook():
    with TestClient(app) as client:
        headers = auth(client)
        centre = client.get("/centres").json()[0]
        appointment = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        booking = client.post("/bookings", headers=headers, json={"centre_id": centre["id"], "diagnostic_test_id": centre["tests"][0]["id"], "appointment_at": appointment}).json()
        event = {"event_id": "evt_001", "booking_id": booking["id"], "provider_reference": "pay_001", "status": "SUCCESS", "amount": booking["amount"]}
        webhook_headers = {"X-Webhook-Secret": "test-webhook-secret"}
        first = client.post("/payments/webhook", headers=webhook_headers, json=event)
        repeated = client.post("/payments/webhook", headers=webhook_headers, json=event)
        assert first.status_code == 200
        assert repeated.status_code == 200
        assert first.json()["id"] == repeated.json()["id"]
        assert client.get("/bookings", headers=headers).json()[0]["status"] == "CONFIRMED"


def test_cannot_pay_another_users_booking():
    with TestClient(app) as client:
        owner_headers = auth(client)
        centre = client.get("/centres").json()[0]
        booking = client.post("/bookings", headers=owner_headers, json={"centre_id": centre["id"], "diagnostic_test_id": centre["tests"][0]["id"], "appointment_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}).json()
        attacker = client.post("/auth/signup", json={"email": "other@example.com", "password": "safe-password", "full_name": "Other User"}).json()
        response = client.post("/payments", headers={"Authorization": f"Bearer {attacker['access_token']}"}, json={"booking_id": booking["id"], "simulate_status": "SUCCESS"})
        assert response.status_code == 403
