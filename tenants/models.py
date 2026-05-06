from django.db import models
from django.contrib.gis.db import models as gis_models
from django_tenants.models import TenantMixin, DomainMixin
from core.models import BaseModel


class City(TenantMixin):
    """
    The Tenant model. Each City will have its own schema in Postgres.
    """
    name = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True, help_text='Unique city code, e.g. MUM, DEL.')
    is_active = models.BooleanField(default=True)
    timezone = models.CharField(max_length=50, default='UTC')
    created_at = models.DateTimeField(auto_now_add=True)

    # auto_create_schema=True by default in TenantMixin
    
    class Meta:
        ordering = ['name']
        verbose_name = 'City'
        verbose_name_plural = 'Cities'

    def __str__(self):
        return f'{self.name} ({self.code})'


class Domain(DomainMixin):
    """
    Required for django-tenants to route requests.
    Example: mumbai.dairy.com
    """
    pass


class Zone(BaseModel):
    """
    Geographic zone within a city schema.
    """
    name = models.CharField(max_length=100)
    boundary = gis_models.PolygonField(
        srid=4326,
        null=True,
        blank=True,
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class HolidayCalendar(BaseModel):
    """
    City-specific holidays within the schema.
    """
    name = models.CharField(max_length=200)
    date = models.DateField()
    is_recurring = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['date']
        unique_together = [('date',)]

    def __str__(self):
        return f'{self.name} — {self.date}'
