from django.db import models
from django.contrib.gis.db import models as gis_models
from core.models import BaseModel
from django.conf import settings


class DriverLocation(BaseModel):
    """
    Stores the LAST KNOWN location of a driver.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='current_location'
    )
    location = gis_models.PointField(srid=4326)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Live: {self.user.get_full_name()} ({self.location.y}, {self.location.x})"


class DriverTrail(models.Model):
    """
    Stores historical breadcrumbs for route replay.
    Not inheriting from BaseModel to keep it lightweight.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trails'
    )
    location = gis_models.PointField(srid=4326)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
        ]

    def __str__(self):
        return f"Trail: {self.user.username} @ {self.timestamp}"
