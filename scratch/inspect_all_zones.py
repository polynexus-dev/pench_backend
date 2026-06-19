import os
import sys
import django

sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context
from routing.models import Zone, Driver
from inventory.models import Warehouse
from accounts.models import User

schema = "pench_nagpur"
with schema_context(schema):
    connection.set_schema(schema)
    
    print("=== WAREHOUSES ===")
    warehouses = Warehouse.objects.all()
    print(f"Total: {len(warehouses)}")
    for w in warehouses:
        print(f"ID: {w.id} | Name: {w.name} | Lat: {w.latitude} | Lng: {w.longitude}")
        
    print("\n=== DRIVERS ===")
    drivers = Driver.objects.all().select_related('user', 'warehouse')
    print(f"Total: {len(drivers)}")
    for d in drivers:
        print(f"Driver Username: {d.user.username} | Warehouse: {d.warehouse.name if d.warehouse else 'None'} | Available: {d.is_available}")
        
    print("\n=== ZONES ===")
    zones = Zone.objects.all().select_related('assigned_driver')
    print(f"Total: {len(zones)}")
    for z in zones:
        cust_count = z.customers.count()
        print(f"Zone Name: {z.name} | Driver: {z.assigned_driver.username if z.assigned_driver else 'None'} | Customers Assigned: {cust_count}")
