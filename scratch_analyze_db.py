
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from tenants.models import City
from accounts.models import User
from django_tenants.utils import schema_context

cities = City.objects.all()
print(f"Available Cities/Schemas: {[c.schema_name for c in cities]}")

for city in cities:
    if city.schema_name == 'public':
        continue
        
    print(f"\nAnalyzing Schema: {city.schema_name} ({city.name})")
    try:
        with schema_context(city.schema_name):
            from orders.models import Order, OrderStatus
            drivers = User.objects.filter(groups__name='Drivers')
            print(f" - Drivers found: {drivers.count()}")
            driver_info = []
            for d in drivers[:3]:
                driver_info.append({'username': d.username, 'id': str(d.id)})
                print(f"   * Driver: {d.username} (ID: {d.id})")
                
            pending_orders = Order.objects.filter(status=OrderStatus.PENDING)
            print(f" - Pending Orders: {pending_orders.count()}")
            order_ids = []
            for o in pending_orders[:5]:
                order_ids.append(str(o.id))
                print(f"   * Order ID: {o.id} (Customer: {o.customer.name})")
                
            if driver_info and order_ids:
                print("\n--- SUGGESTED PAYLOAD ---")
                import json
                payload = {
                    "name": f"Morning Delivery {city.name}",
                    "date": "2026-05-16",
                    "driver_id": driver_info[0]['id'],
                    "order_ids": order_ids
                }
                print(json.dumps(payload, indent=2))
                print("--------------------------")
    except Exception as e:
        print(f"Error analyzing schema {city.schema_name}: {e}")
    
