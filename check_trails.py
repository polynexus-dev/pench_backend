import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from tracking.models import DriverTrail
from django_tenants.utils import schema_context

with schema_context('pune'):
    count = DriverTrail.objects.count()
    print(f'Total trails in Pune: {count}')
    if count > 0:
        print("Last 5 trails:")
        for t in DriverTrail.objects.all().order_by('-timestamp')[:5]:
            print(f"  {t.timestamp} - {t.location}")
