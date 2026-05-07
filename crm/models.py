import uuid
from django.db import models
from core.models import BaseModel

try:
    from django.contrib.gis.db import models as gis_models
    HAS_GIS = True
except Exception:
    HAS_GIS = False

class Customer(BaseModel):
    """CRM customer — Scoped to schema."""
    name = models.CharField(max_length=200)
    user = models.OneToOneField(
        'accounts.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='customer_profile'
    )
    company = models.CharField(max_length=200, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    
    # Conditional GIS field
    if HAS_GIS:
        location = gis_models.PointField(
            srid=4326,
            null=True,
            blank=True,
            help_text='Customer geolocation (longitude, latitude).'
        )
    else:
        location = models.JSONField(null=True, blank=True, help_text='GIS Disabled: Falling back to JSON.')

    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    qr_code_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    def save(self, *args, **kwargs):
        if not self.qr_code_id:
            self.qr_code_id = uuid.uuid4()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['name']
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'

    def __str__(self):
        return f'{self.name} ({self.company or self.email})'

class Lead(BaseModel):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    referred_by = models.ForeignKey(
        Customer, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='referrals'
    )
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='new')

    def __str__(self):
        return f'Lead: {self.name} (Ref: {self.referred_by.name if self.referred_by else "None"})'
