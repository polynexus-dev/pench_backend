import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django_tenants.utils import schema_context
from orders.models import Order, Route
import datetime

print("Cleaning up database test entries...")
with schema_context('pench-nagpur'):
    today = datetime.date.today()
    Route.objects.filter(delivery_date=today).delete()
    Order.objects.filter(scheduled_delivery_date=today).delete()
    print("Database cleaned successfully!")
