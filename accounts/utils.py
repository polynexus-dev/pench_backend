import secrets
import string
import logging
from django.utils import timezone
from datetime import timedelta
from .models import OTP

logger = logging.getLogger(__name__)


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
