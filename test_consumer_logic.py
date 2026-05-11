import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from tracking.models import DriverLocation
from django_tenants.utils import schema_context
from asgiref.sync import async_to_sync

from django.contrib.gis.geos import Point
from tracking.models import DriverTrail
import datetime

def test_consumer_logic():
    print("Testing synchronous call...")
    try:
        with schema_context('pune'):
            today = datetime.date.today()
            trails = DriverTrail.objects.filter(
                user_id=1,
                timestamp__date=today
            ).order_by('timestamp')
            
            print(f"Trails found for today ({today}): {trails.count()}")
            if trails.count() == 0:
                print("Checking without date filter...")
                all_t = DriverTrail.objects.filter(user_id=1).count()
                print(f"Total trails for user_id=1: {all_t}")
            
    except Exception as e:
        print(f"Sync call FAILED: {e}")

if __name__ == "__main__":
    test_consumer_logic()
