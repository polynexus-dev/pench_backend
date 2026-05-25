import os
import django
import sys

sys.path.append(os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django_tenants.utils import schema_context
from orders.models import Order, Route, RouteStop

def check():
    with schema_context('nagpur'):
        routes = Route.objects.filter(delivery_date='2026-05-25')
        print(f"=== Found {routes.count()} routes on 2026-05-25 ===")
        for r in routes:
            print(f"Route: {r.name} (ID: {r.id}, Status: {r.status}, Started: {r.started_at}, Completed: {r.completed_at})")
            stops = r.stops.all()
            print(f"  Stops Count: {stops.count()}")
            for s in stops:
                print(f"    - Stop #{s.sequence_number}: Customer: {s.order.customer.name}, Order ID: {s.order.id}, Status: {s.order.status}, Delivered At: {s.order.delivered_at}")

if __name__ == '__main__':
    check()
