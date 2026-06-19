import os
import sys
import django

sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context
from orders.models import Order, Route, RouteStop

schema = "pench_nagpur"
with schema_context(schema):
    connection.set_schema(schema)
    
    print("=== ALL ROUTES ===")
    routes = Route.objects.all().order_by('-delivery_date', '-created_at')
    print(f"Total routes found: {routes.count()}")
    for r in routes:
        print(f"\nRoute ID: {r.id} | Name: {r.name} | Driver: {r.driver.username if r.driver else 'None'} | Date: {r.delivery_date} | Status: {r.status} | Is Completed: {r.is_completed} | Started At: {r.started_at}")
        stops = RouteStop.objects.filter(route=r).order_by('sequence_number')
        print(f"Stops count: {stops.count()}")
        # print first few stops
        for s in list(stops)[:15]:
            order = s.order
            print(f"  Stop #{s.sequence_number} | Order ID: {order.id} | Cust: {order.customer.name} | Status: {order.status} | Delivered At: {order.delivered_at}")
