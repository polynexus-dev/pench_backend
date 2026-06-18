import os
import sys
import django
import datetime

sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django_tenants.utils import schema_context
from orders.models import Order, Route

today = datetime.date(2026, 6, 18)
print("Checking local database for date:", today)

with schema_context("pench_nagpur"):
    orders = Order.objects.filter(scheduled_delivery_date=today)
    print(f"Total local orders for {today}: {orders.count()}")
    for o in orders:
        print(f"  Order ID: {o.id} | Customer: {o.customer.name} | Status: {o.status}")
        
    routes = Route.objects.filter(delivery_date=today)
    print(f"Total local routes for {today}: {routes.count()}")
    for r in routes:
        print(f"  Route ID: {r.id} | Name: {r.name} | Stops count: {r.stops.count()}")
        for s in r.stops.all():
            print(f"    - Seq {s.sequence_number} | Order ID: {s.order.id} | Customer: {s.order.customer.name}")
