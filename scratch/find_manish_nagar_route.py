import os
import django
import sys

sys.path.append(os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django_tenants.utils import schema_context
from tenants.models import City
from orders.models import Route

def check():
    cities = City.objects.all()
    for c in cities:
        with schema_context(c.schema_name):
            routes = Route.objects.filter(name__icontains='Manish Nagar')
            if routes.exists():
                print(f"\n=== Found {routes.count()} Manish Nagar routes in schema: {c.schema_name} ===")
                for r in routes:
                    print(f"Route: {r.name} (Date: {r.delivery_date})")
                    stops = r.stops.all()
                    for s in stops:
                        order = s.order
                        print(f"    - Stop #{s.sequence_number}: Customer: {order.customer.name}")
                        print(f"      * Order ID: {order.id}")
                        print(f"      * Scheduled Date: {order.scheduled_delivery_date}")
                        print(f"      * Created At: {order.created_at}")
                        print(f"      * Status: {order.status}")
                        print(f"      * Delivered At: {order.delivered_at}")

if __name__ == '__main__':
    try:
        check()
    except Exception as e:
        print(f"Error: {e}")
