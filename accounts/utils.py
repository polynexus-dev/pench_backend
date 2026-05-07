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
    """
    code = ''.join(secrets.choice(string.digits) for _ in range(6))
    expires_at = timezone.now() + timedelta(minutes=10)
    
    otp = OTP.objects.create(
        phone=phone,
        code=code,
        expires_at=expires_at
    )
    
    # Secure logging: only log that it was generated, not the code itself
    logger.info(f"OTP generated for {phone}")
    
    return otp
