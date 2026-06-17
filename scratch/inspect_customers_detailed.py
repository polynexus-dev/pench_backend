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
from subscriptions.models import Subscription

schema = "pench_nagpur"
print(f"--- DETAILED DIAGNOSTIC REPORT FOR SCHEMA: {schema} ---")

with schema_context(schema):
    connection.set_schema(schema)
    
    customers = Customer.objects.all().order_by('name')
    print(f"Total Customers in DB: {len(customers)}")
    
    print("\n--- Customers with Zones or Locations ---")
    for c in customers:
        if c.zone or c.location or c.trial_approved:
            print(f"Name: {c.name}")
            print(f"  ID: {c.id}")
            print(f"  Phone: {c.phone} | Email: {c.email}")
            print(f"  is_active: {c.is_active} | is_new: {c.is_new} | trial_approved: {c.trial_approved}")
            print(f"  Zone: {c.zone.name if c.zone else 'None'} | Location: {c.location}")
            print(f"  User Linked: {c.user.username if c.user else 'None'}")
            print("-" * 40)
            
    print("\n--- Customers with Duplicates (same name or phone) ---")
    checked = set()
    for c in customers:
        if c.id in checked:
            continue
        dups = Customer.objects.filter(phone=c.phone).exclude(phone='') if c.phone else Customer.objects.none()
        if not dups.exists() and c.name:
            dups = Customer.objects.filter(name__iexact=c.name.strip())
        if dups.count() > 1:
            print(f"Duplicate group for Name '{c.name}' / Phone '{c.phone}':")
            for d in dups:
                checked.add(d.id)
                print(f"  - ID: {d.id} | Name: {d.name} | is_new: {d.is_new} | trial_approved: {d.trial_approved} | Zone: {d.zone.name if d.zone else 'None'} | Loc: {d.location} | User: {d.user.username if d.user else 'None'}")
            print("-" * 40)
