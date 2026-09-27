# Diagnostic Test Booking Service

A FastAPI backend service for diagnostic test bookings and simulated payments.

The service provides JWT-based authentication, diagnostic centres and tests, booking management, simulated payments, an idempotent payment webhook, Redis caching, and Celery background processing.

## Tech Stack

* Python
* FastAPI
* SQLAlchemy
* PostgreSQL
* SQLite for tests
* JWT authentication
* Redis
* Celery
* Docker & Docker Compose
* Pytest
* OpenAPI / Swagger

---

## Features

* User signup and login
* JWT-based authentication
* Diagnostic centre and test catalogue
* Admin-protected catalogue management
* Authenticated diagnostic test bookings
* Booking status management
* Simulated payment processing
* Payment webhook with idempotent event handling
* Payment amount validation
* User-level authorization
* Redis catalogue caching
* Celery post-payment notification task
* Dockerized development environment
* Automated API tests
* Swagger/OpenAPI documentation

---

## Project Structure

```text
backend/
├── app/
│   ├── cache.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   ├── security.py
│   └── tasks.py
├── tests/
│   └── test_api.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
└── .gitignore
```

---

# Local Setup

## 1. Create virtual environment

### Windows PowerShell

```powershell
cd backend

python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
cd backend

python -m venv .venv
source .venv/bin/activate
```

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

## 3. Environment variables

The application uses the following environment variables:

```text
JWT_SECRET=replace-with-a-strong-secret
WEBHOOK_SECRET=replace-with-a-strong-webhook-secret
ADMIN_EMAIL=admin@eve.local
ADMIN_PASSWORD=replace-with-a-strong-password
```

For local development, the application can use SQLite by default.

For PostgreSQL, set:

```text
DATABASE_URL=postgresql+psycopg://user:password@localhost/eve
```

Do not commit `.env` or real secrets to GitHub.

## 4. Start the application

```bash
uvicorn app.main:app --reload
```

The API starts at:

```text
http://127.0.0.1:8000
```

Swagger documentation:

```text
http://127.0.0.1:8000/docs
```

---

# Docker

The project includes a Docker Compose setup containing:

* FastAPI API
* PostgreSQL
* Redis
* Celery worker

Start the complete stack with:

```bash
docker compose up --build
```

The API is available at:

```text
http://127.0.0.1:8000
```

The Docker Compose configuration provides the database and Redis services required by the application.

For deployment, strong values should be provided for:

```text
JWT_SECRET
WEBHOOK_SECRET
ADMIN_PASSWORD
```

---

# Authentication

## Signup

```http
POST /auth/signup
```

Creates a new user account.

## Login

```http
POST /auth/login
```

Authenticates the user and returns a JWT token.

Protected endpoints use:

```http
Authorization: Bearer <token>
```

JWT authentication uses the `HS256` algorithm.

---

# Diagnostic Centres

## List centres

```http
GET /centres
```

Returns the available diagnostic centres and their tests.

## Get a centre

```http
GET /centres/{id}
```

Returns a specific diagnostic centre and its available tests.

Diagnostic centres contain diagnostic tests, and each diagnostic test has a price.

Catalogue management operations are restricted to admin users.

---

# Bookings

## Create a booking

```http
POST /bookings
```

Requires authentication.

Example request:

```json
{
  "centre_id": 1,
  "diagnostic_test_id": 1,
  "appointment_at": "2026-10-01T09:30:00+00:00"
}
```

A new booking is created with:

```text
PENDING
```

The booking stores the current test price as its `amount`.

This preserves the amount of an existing booking even if the catalogue price changes later.

## List bookings

```http
GET /bookings
```

Returns the authenticated user's bookings.

## Cancel a booking

```http
POST /bookings/{id}/cancel
```

A user can cancel their own pending booking.

Users cannot access or modify another user's bookings through the booking APIs.

---

# Booking Statuses

The application supports the following booking states:

```text
PENDING
CONFIRMED
FAILED
CANCELLED
```

Typical payment transitions are:

```text
PENDING → CONFIRMED
PENDING → FAILED
```

Cancellation transitions a pending booking to:

```text
PENDING → CANCELLED
```

---

# Simulated Payments

The application does not integrate with a real payment gateway.

Instead, payment processing is simulated through:

```http
POST /payments
```

The endpoint can process the authenticated user's pending booking and produce either:

```text
SUCCESS
```

or:

```text
FAILED
```

The booking is updated according to the payment result.

A successful payment confirms the booking, while a failed payment marks it as failed.

---

# Payment Webhook

The application also exposes a provider webhook:

```http
POST /payments/webhook
```

The webhook requires the configured secret in:

```http
X-Webhook-Secret: <your-webhook-secret>
```

Example payload:

```json
{
  "event_id": "evt_1001",
  "booking_id": 1,
  "provider_reference": "pay_1001",
  "status": "SUCCESS",
  "amount": 450
}
```

The webhook validates:

* Webhook secret
* Booking existence
* Booking payment state
* Payment amount

---

## Webhook Idempotency

Webhook events are tracked using `ProcessedWebhookEvent`.

Each `event_id` is unique.

If the same webhook event is received again, the application checks whether it has already been processed and returns the existing payment instead of creating another payment.

The payment provider reference is also unique.

This prevents duplicate payment records when a provider retries the same webhook.

The webhook processing commits the processed event and payment/status update together.

---

# Important Payment Flow

There are two payment-related endpoints:

### Simulated application payment

```text
POST /payments
```

Used to simulate the payment process for a user's pending booking.

### Provider webhook

```text
POST /payments/webhook
```

Used to process a payment result received from the simulated provider.

For testing webhook idempotency directly, create a booking first and then send the webhook while the booking is still `PENDING`.

---

# Authorization & Edge Cases

The application handles several important edge cases:

* Invalid request data
* Invalid booking IDs
* Non-existent bookings
* Unauthorized access to another user's booking
* Payment attempts for bookings that are not pending
* Invalid webhook secret
* Payment amount mismatch
* Repeated webhook events
* Duplicate provider references
* Failed payments

Users can only access and modify their own bookings.

Admin-only catalogue operations are protected using the user's `is_admin` flag.

---

# Database Design

The main database models are:

```text
User
DiagnosticCentre
DiagnosticTest
Booking
Payment
ProcessedWebhookEvent
```

### User

Stores application users and authentication information.

### DiagnosticCentre

Represents a diagnostic centre and its available tests.

### DiagnosticTest

Represents an individual diagnostic test and its price.

### Booking

Stores:

* User
* Diagnostic centre
* Diagnostic test
* Appointment time
* Amount
* Booking status

The booking stores the test price at booking time.

### Payment

Stores the payment result associated with a booking.

`provider_reference` is unique.

### ProcessedWebhookEvent

Stores webhook event IDs that have already been processed.

`event_id` is unique and is used for webhook idempotency.

---

# Redis Caching

Redis is used to cache the public diagnostic centre catalogue.

The cache lifetime is:

```text
60 seconds
```

Catalogue changes invalidate the relevant cache.

If Redis is unavailable, the application falls back to the database.

---

# Celery Background Tasks

The application uses Celery for post-payment notification work.

The notification task is queued after the payment transaction is committed.

The current task logs the notification event and provides an integration point for future email/SMS notification functionality.

The task also supports retry handling.

---

# API Documentation

FastAPI provides interactive API documentation automatically.

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

OpenAPI schema:

```text
http://127.0.0.1:8000/openapi.json
```

---

# Tests

Run the test suite with:

```bash
pytest -q
```

The tests include:

* Booking creation
* Successful payment webhook
* Idempotent webhook processing
* Repeated webhook events
* Booking confirmation
* Cross-user payment authorization

The webhook test sends the same event more than once and verifies that the payment is not duplicated.

---

# Design Decisions

### Price snapshot

The booking stores its own `amount` instead of always reading the current diagnostic test price.

This prevents later catalogue price changes from changing the amount of an existing booking.

### Webhook idempotency

Processed webhook events are stored separately and have a unique event ID.

Payment provider references are also unique.

Together these constraints prevent duplicate payment processing.

### Authorization

Booking ownership is checked before payment or cancellation operations.

### Cache fallback

Redis improves catalogue reads, but Redis availability is not required for the application to retrieve catalogue data.

### Transaction boundary

Payment processing and webhook handling commit database state before queuing the post-payment notification task.

---

# Assumptions

* Appointment timestamps are timezone-aware.
* Appointment availability scheduling is not modelled.
* Payments are simulated and no real payment gateway is integrated.
* SQLite can be used for local development/testing.
* PostgreSQL is used in the Docker Compose environment.
* Payment amounts currently use floating-point values.
* The Celery notification task currently logs instead of sending real email/SMS notifications.

---

# Future Improvements

If this service were extended for production use, I would consider:

* Alembic database migrations
* Decimal-based currency handling
* PostgreSQL integration tests
* Structured logging and metrics
* Rate limiting
* Signed webhook payload verification
* More comprehensive concurrency tests
* An outbox pattern for reliable background task delivery
* Appointment availability and slot management
* Pagination for larger datasets

---

# Running Tests

```bash
cd backend
pytest -q
```

For Docker-based development:

```bash
docker compose up --build
```

Then the API can be tested through Swagger:

```text
http://127.0.0.1:8000/docs
```

---


