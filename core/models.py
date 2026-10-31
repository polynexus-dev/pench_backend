from django.db import models
import uuid


class TimestampedModel(models.Model):
    """Abstract base model providing created_at and updated_at timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """Abstract base model using UUID as primary key."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimestampedModel):
    """Convenience base combining UUID pk + timestamps."""

    class Meta:
        abstract = True


class AppVersionConfig(TimestampedModel):
    """
    Per app/platform version policy used to force or suggest mobile app updates.
    Lives in the public schema (core is a shared app), so one config covers all cities.
    """

    class App(models.TextChoices):
        PENCH = "pench", "Pench App (all roles)"
        CUSTOMER = "customer", "Customer App"
        DELIVERY = "delivery", "Delivery App"

    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    app = models.CharField(max_length=20, choices=App.choices)
    platform = models.CharField(max_length=10, choices=Platform.choices)
    min_supported_version = models.CharField(
        max_length=20,
        help_text="Versions below this are blocked (force update), e.g. 2.3.0.",
    )
    latest_version = models.CharField(
        max_length=20,
        help_text="Versions below this get a dismissible update prompt.",
    )
    store_url = models.URLField(max_length=500)
    update_message = models.TextField(blank=True)
    maintenance_mode = models.BooleanField(
        default=False, help_text="Block the app entirely (e.g. during downtime)."
    )
    maintenance_message = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    # ── Automatic store sync (core.tasks.sync_store_versions) ──
    auto_force_store_version = models.BooleanField(
        default=True,
        help_text="Automatically force-update users when a newer version is published on the store.",
    )
    store_app_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Play Store package name (android) or numeric App Store ID (ios).",
    )
    force_delay_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Minimum version always tracks the latest store version. Optionally wait this "
        "long after a new store version is detected before forcing it (0 = force immediately).",
    )
    store_version = models.CharField(max_length=20, blank=True, editable=False)
    store_version_detected_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_store_check_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_store_check_error = models.TextField(blank=True, editable=False)

    class Meta:
        unique_together = ("app", "platform")
        verbose_name = "App Version Config"
        verbose_name_plural = "App Version Configs"

    def __str__(self):
        return (
            f"{self.get_app_display()} ({self.get_platform_display()}) "
            f"min={self.min_supported_version} latest={self.latest_version}"
        )

    def clean(self):
        from django.core.exceptions import ValidationError
        from core.app_version import parse_version

        errors = {}
        min_v = parse_version(self.min_supported_version)
        latest_v = parse_version(self.latest_version)
        if min_v is None:
            errors["min_supported_version"] = "Invalid version, expected e.g. 2.3.0"
        if latest_v is None:
            errors["latest_version"] = "Invalid version, expected e.g. 2.3.0"
        if min_v and latest_v and min_v > latest_v:
            errors["min_supported_version"] = "Cannot be greater than latest version."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        from core.app_version import clear_cache

        super().save(*args, **kwargs)
        clear_cache(self.app, self.platform)

    def delete(self, *args, **kwargs):
        from core.app_version import clear_cache

        app, platform = self.app, self.platform
        result = super().delete(*args, **kwargs)
        clear_cache(app, platform)
        return result
