from django.db import models
from django.contrib.gis.db import models as gis_models
from core.models import BaseModel


class Customer(BaseModel):
    """CRM customer — Scoped to schema."""

    name = models.CharField(max_length=200)
    company = models.CharField(max_length=200, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    
    # GIS: point geometry for frontend map (SRID 4326 = WGS84)
    location = gis_models.PointField(
        srid=4326,
        null=True,
        blank=True,
        help_text='Customer geolocation (longitude, latitude).'
    )

    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'

    def __str__(self):
        return f'{self.name} ({self.company or self.email})'
