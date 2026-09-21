import secrets
import string
import logging
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import OTP

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """
    Resolves the client IP for audit logging.

    X-Forwarded-For is client-suppliable and only reflects reality when a
    trusted reverse proxy sets/overwrites it, so it's only honored when
    settings.TRUST_X_FORWARDED_FOR is enabled for that deployment; otherwise
    REMOTE_ADDR is used so a client can't spoof its own logged IP.
    """
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def generate_otp(phone):
    """
    Generates a 6-digit OTP using cryptographically secure random and saves it to the database.
    Enforces previous OTP invalidation.
    """
    now = timezone.now()

    # 2. Invalidate previous unused active OTPs for the same phone number
    OTP.objects.filter(phone=phone, is_used=False).update(is_used=True)

    # 3. Generate new OTP
    code = "".join(secrets.choice(string.digits) for _ in range(6))
    expires_at = now + timedelta(minutes=10)

    otp = OTP.objects.create(phone=phone, code=code, expires_at=expires_at)

    # Secure logging: only log that it was generated, not the code itself
    logger.info(f"OTP generated for {phone}")

    return otp
