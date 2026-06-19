import os
import sys
import django

sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context
from tenants.models import City
from crm.models import Customer
from orders.models import Order, Route, RouteStop

print("--- DIAGNOSTIC CUSTOMER MERGE/ROUTE REPORT ---")

cities = City.objects.all()
for city in cities:
    schema = city.schema_name
    if schema == "public":
        continue
    print(f"\n================ SCHEMA: {schema} (City: {city.name}) ================")
    
    with schema_context(schema):
        connection.set_schema(schema)
        
        all_custs = Customer.objects.all()
        print(f"Total customers in DB: {all_custs.count()}")
        
        # Customers with null zone
        null_zone_custs = all_custs.filter(zone__isnull=True)
        print(f"Customers with no zone assigned: {null_zone_custs.count()}")
        for c in null_zone_custs[:10]:
            print(f"  - {c.name} (Phone: {c.phone}, Created: {c.created_at}, is_new={c.is_new}, trial_approved={c.trial_approved})")
            
        # New customers with trial_approved=False
        unapproved_new_custs = all_custs.filter(is_new=True, trial_approved=False)
        print(f"New customers with trial NOT approved: {unapproved_new_custs.count()}")
        for c in unapproved_new_custs[:10]:
            print(f"  - {c.name} (Phone: {c.phone}, Zone: {c.zone.name if c.zone else 'None'}, Created: {c.created_at})")
            
        # Active subscriptions / pending orders
        pending_orders = Order.objects.filter(status__in=["pending", "confirmed"])
        print(f"Pending/Confirmed orders in DB: {pending_orders.count()}")
        
        unassigned_orders = pending_orders.filter(route_stop__isnull=True)
        print(f"Unassigned pending/confirmed orders (not on any route): {unassigned_orders.count()}")
        for o in unassigned_orders[:10]:
            cust = o.customer
            print(f"  - Order #{o.id} for Customer: {cust.name} (is_new={cust.is_new}, trial_approved={cust.trial_approved}, zone={cust.zone.name if cust.zone else 'None'}, date={o.scheduled_delivery_date})")

        # Active routes
        routes = Route.objects.filter(is_completed=False)
        print(f"Active (incomplete) routes: {routes.count()}")
        for r in routes:
            print(f"  - Route ID {r.id}: {r.name} (Date: {r.delivery_date}, Status: {r.status}, Stops count: {r.stops.count()})")
