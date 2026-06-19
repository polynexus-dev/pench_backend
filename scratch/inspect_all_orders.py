import os
import sys
import django

sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context
from crm.models import Customer
from orders.models import Order, Route, RouteStop
from subscriptions.models import Subscription

schema = "pench_nagpur"
with schema_context(schema):
    connection.set_schema(schema)
    
    print("=== ALL ORDERS ===")
    orders = Order.objects.all().select_related('customer')
    print(f"Total Orders: {len(orders)}")
    for o in orders:
        rs = RouteStop.objects.filter(order=o).first()
        print(f"Order ID: {o.id} | Customer: {o.customer.name if o.customer else 'None'} | Date: {o.scheduled_delivery_date} | Status: {o.status} | Route: {rs.route.name if rs else 'None'}")
        
    print("\n=== ALL SUBSCRIPTIONS ===")
    subs = Subscription.objects.all().select_related('customer')
    print(f"Total Subscriptions: {len(subs)}")
    for s in subs:
        print(f"Sub ID: {s.id} | Customer: {s.customer.name} | Status: {s.status}")
