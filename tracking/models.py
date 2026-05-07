from django.db import models
from core.models import BaseModel
from django.conf import settings

try:
    from django.contrib.gis.db import models as gis_models
    HAS_GIS = getattr(settings, 'HAS_GDAL', False)
except Exception:
    HAS_GIS = False

class DriverLocation(BaseModel):
    """
    Stores the LAST KNOWN location of a driver.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='current_location'
    )
    
    if HAS_GIS:
        location = gis_models.PointField(srid=4326)
    else:
        location = models.JSONField() # Store as [lat, lng] or similar
        
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Live Location: {self.user.get_full_name()}"

class DriverTrail(models.Model):
    """
    Stores historical breadcrumbs for route replay.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trails'
    )
    
    if HAS_GIS:
        location = gis_models.PointField(srid=4326)
    else:
        location = models.JSONField()
        
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
        ]

    def __str__(self):
        return f"Trail: {self.user.username} @ {self.timestamp}"
