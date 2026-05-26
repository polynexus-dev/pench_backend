from django.contrib.auth.models import AbstractUser
from django.db import models


class PortalChoice(models.TextChoices):
    DELIVERY = "delivery", "Delivery Portal"
    ERP = "erp", "ERP Portal"
    BOTH = "both", "Both Portals"


class User(AbstractUser):
    """
    Custom user model extending AbstractUser.
    Controls access to ERP vs Delivery portals.
    """

    is_erp_user = models.BooleanField(
        default=False, help_text="Grants access to the ERP portal."
    )
    is_driver = models.BooleanField(
        default=False, help_text="Designates this user as a delivery driver."
    )
    is_customer = models.BooleanField(
        default=False, help_text="Designates this user as a CRM customer."
    )
    tenant_schema = models.CharField(
        max_length=63,
        null=True,
        blank=True,
        help_text="The schema name of the tenant this customer belongs to.",
    )
    portal = models.CharField(
        max_length=10,
        choices=PortalChoice.choices,
        default=PortalChoice.ERP,
        help_text="Primary portal this user accesses.",
    )
    phone = models.CharField(max_length=20, null=True, blank=True, unique=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.email})"

    def save(self, *args, **kwargs):
        # Prevent uniqueness collision of empty/blank phone strings by converting them to None
        if self.phone == "":
            self.phone = None

        # Auto-set portal based on flags
        if self.is_driver:
            self.portal = PortalChoice.DELIVERY
        elif self.is_erp_user:
            self.portal = PortalChoice.ERP
        super().save(*args, **kwargs)


class OTP(models.Model):
    """
    Temporary OTP codes for phone-based login.
    """

    phone = models.CharField(max_length=20)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "OTP"
        verbose_name_plural = "OTPs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.phone}: {self.code}"
