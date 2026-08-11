from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


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
    email = models.EmailField(unique=True, null=True, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    password_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of when the user's password was last changed.",
    )

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.email})"

    def set_password(self, raw_password):
        super().set_password(raw_password)
        self.password_changed_at = timezone.now()

    def save(self, *args, **kwargs):
        # Prevent uniqueness collision of empty/blank phone/email strings by converting them to None
        if self.phone == "":
            self.phone = None
        if self.email == "":
            self.email = None

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


class PasswordChangeLog(models.Model):
    """
    Log of all password changes across users for auditing and troubleshooting credential complaints.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="password_change_logs"
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="passwords_changed_by_me",
        help_text="User who initiated/executed the password change.",
    )
    source = models.CharField(
        max_length=50,
        default="set_password",
        help_text="Where the password was changed from (e.g. self_reset, admin_update, driver_credentials_update).",
    )
    ip_address = models.CharField(max_length=45, null=True, blank=True)

    class Meta:
        verbose_name = "Password Change Log"
        verbose_name_plural = "Password Change Logs"
        ordering = ["-changed_at"]

    def __str__(self):
        return f"Password change for {self.user.username} at {self.changed_at}"


class LoginAuditLog(models.Model):
    """
    Log of login attempts to help correlate credential issues against password change timestamps.
    """
    username_or_phone = models.CharField(max_length=150)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_audit_logs",
    )
    attempt_time = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=40,
        choices=[
            ("SUCCESS", "Success"),
            ("FAILED_INVALID_PASSWORD", "Failed - Invalid Password"),
            ("FAILED_USER_NOT_FOUND", "Failed - User Not Found"),
            ("FAILED_INACTIVE", "Failed - User Inactive"),
        ],
    )
    ip_address = models.CharField(max_length=45, null=True, blank=True)
    user_agent = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = "Login Audit Log"
        verbose_name_plural = "Login Audit Logs"
        ordering = ["-attempt_time"]

    def __str__(self):
        return f"Login attempt ({self.status}) for {self.username_or_phone} at {self.attempt_time}"

