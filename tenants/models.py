from django.db import models
from django.conf import settings
from django_tenants.models import TenantMixin, DomainMixin
from core.models import BaseModel

try:
    from django.contrib.gis.db import models as gis_models

    HAS_GIS = getattr(settings, "HAS_GDAL", False)
except Exception:
    HAS_GIS = False


class Company(BaseModel):
    """
    A logical grouping of Cities (Tenants) under one corporate entity.
    This resides in the public schema.
    """

    name = models.CharField(max_length=200)
    code = models.CharField(
        max_length=50, unique=True, help_text="Unique company code, e.g. RELIANCE"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class City(TenantMixin):
    """
    The Tenant model. Each City will have its own schema in Postgres.
    """

    auto_create_schema = False

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="cities", null=True, blank=True
    )
    name = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    code = models.CharField(max_length=20, help_text="Unique city code, e.g. MUM, DEL.")
    is_active = models.BooleanField(default=True)
    timezone = models.CharField(max_length=50, default="Asia/Kolkata")
    require_pod = models.BooleanField(
        default=False,
        help_text="If enabled, drivers must upload a photo to mark an order as delivered.",
    )

    if HAS_GIS:
        boundary = gis_models.PolygonField(
            srid=4326,
            null=True,
            blank=True,
            help_text="Geofencing boundary for this city.",
        )
    else:
        boundary = models.JSONField(
            null=True, blank=True, help_text="GIS Disabled: Falling back to JSONField."
        )

    created_at = models.DateTimeField(auto_now_add=True)

    # auto_create_schema=True by default in TenantMixin

    class Meta:
        ordering = ["name"]
        verbose_name = "City"
        verbose_name_plural = "Cities"
        unique_together = (("company", "code"),)

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        if not self.schema_name:
            import re

            def clean_name(val):
                if not val:
                    return ""
                val = val.lower()
                val = re.sub(r"[^a-z0-9_]", "_", val)
                val = re.sub(r"_+", "_", val)
                return val.strip("_")

            clean_city = clean_name(self.name)
            if self.company and clean_city:
                clean_company = clean_name(self.company.code)
                schema_name = f"{clean_company}_{clean_city}"
            elif clean_city:
                schema_name = clean_city
            else:
                schema_name = clean_name(self.code)
            self.schema_name = schema_name[:63]
        super().save(*args, **kwargs)


class Domain(DomainMixin):
    """
    Required for django-tenants to route requests.
    Example: mumbai.dairy.com
    """

    pass


class HolidayCalendar(BaseModel):
    """
    City-specific holidays within the schema.
    """

    city = models.ForeignKey(
        City, on_delete=models.CASCADE, related_name="holidays", null=True, blank=True
    )
    name = models.CharField(max_length=200)
    date = models.DateField()
    is_recurring = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["date"]
        unique_together = [("city", "date")]

    def __str__(self):
        return f"{self.name} ({self.city.name}) — {self.date}"
