import logging
import os

from celery import Celery

celery_app = Celery("eve", broker=os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0")))
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="UTC")
logger = logging.getLogger(__name__)


@celery_app.task(name="eve.send_booking_payment_notification", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_booking_payment_notification(booking_id: int, status: str) -> None:
    """Placeholder for email/SMS provider integration; retried safely by Celery."""
    logger.info("Payment notification queued", extra={"booking_id": booking_id, "payment_status": status})


def queue_payment_notification(booking_id: int, status: str) -> None:
    """Queue only when the worker is configured; local-only mode remains dependency-free."""
    if os.getenv("CELERY_ENABLED", "false").lower() == "true":
        try:
            send_booking_payment_notification.delay(booking_id, status)
        except Exception:
            # Payment persistence must not be affected by a broker outage. In production,
            # an outbox table would provide durable redelivery instead.
            logger.exception("Could not enqueue payment notification", extra={"booking_id": booking_id})
