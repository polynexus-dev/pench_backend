from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import DriverTrail
from django_tenants.utils import schema_context
from tenants.models import City

@shared_task
def cleanup_old_trails():
    """
    Deletes DriverTrail records older than 30 days for all cities.
    """
    cutoff_date = timezone.now() - timedelta(days=30)
    
    cities = City.objects.all()
    for city in cities:
        with schema_context(city.schema_name):
            deleted_count, _ = DriverTrail.objects.filter(timestamp__lt=cutoff_date).delete()
            print(f"Deleted {deleted_count} old trail records for {city.schema_name}")
