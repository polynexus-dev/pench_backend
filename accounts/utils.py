import random
import logging
from django.utils import timezone
from datetime import timedelta
from .models import OTP

logger = logging.getLogger(__name__)

def generate_otp(phone):
    """
    Generates a 6-digit OTP and saves it to the database.
    """
    code = str(random.randint(100000, 999999))
    expires_at = timezone.now() + timedelta(minutes=10)
    
    otp = OTP.objects.create(
        phone=phone,
        code=code,
        expires_at=expires_at
    )
    
    # In a real app, you would send this via Twilio or another SMS gateway
    # For now, we just log it.
    print(f"\n[OTP SERVICE] CODE FOR {phone}: {code} (Expires: {expires_at})\n")
    logger.info(f"OTP generated for {phone}: {code}")
    
    return otp
