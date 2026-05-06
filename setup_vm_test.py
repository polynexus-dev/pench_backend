import os
import django
import sys
import random
import datetime
import csv

# Add current working directory to sys.path
sys.path.append(os.getcwd())

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django_tenants.utils import schema_context
from accounts.models import User
from routing.models import Driver
from crm.models import Customer
from orders.models import Order, Route
from orders.services import create_optimized_route
from django.contrib.gis.geos import Point

schema_name = 'nagpur'
password = 'admin123'
num_drivers = 7
cust_per_driver = 10

# Center of Nagpur
NAGPUR_LAT = 21.1458
NAGPUR_LNG = 79.0882

print(f"--- STARTING VM TEST SETUP (Nagpur) ---")

credentials = []

with schema_context(schema_name):
    # 1. Create Drivers
    for i in range(1, num_drivers + 1):
        username = f"vm_driver_{i}"
        phone = f"9800000{i:03d}"
        
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'first_name': f'VM',
                'last_name': f'Driver {i}',
                'phone': phone,
                'is_driver': True
            }
        )
        if created:
            user.set_password(password)
            user.save()
        
        Driver.objects.get_or_create(user=user, defaults={'is_active': True})
        
        # 2. Create 10 Customers and Orders for this driver
        order_ids = []
        for j in range(1, cust_per_driver + 1):
            cust_idx = ((i-1) * 10) + j
            cust_name = f"VM Customer {cust_idx}"
            cust_phone = f"880000{cust_idx:04d}"
            
            # Random location around Nagpur center (+/- 0.02 deg ~ 2km)
            lat = NAGPUR_LAT + random.uniform(-0.02, 0.02)
            lng = NAGPUR_LNG + random.uniform(-0.02, 0.02)
            
            customer, _ = Customer.objects.get_or_create(
                phone=cust_phone,
                defaults={
                    'name': cust_name,
                    'address': f'Area {i}, Street {j}, Nagpur',
                    'location': Point(lng, lat)
                }
            )
            
            # Create a pending order
            order = Order.objects.create(
                customer=customer,
                status='pending',
                scheduled_delivery_date=datetime.date.today(),
                total_amount=random.randint(100, 500)
            )
            order_ids.append(str(order.id))
        
        # 3. Create Optimized Route for this driver
        route_name = f"Nagpur Route - {username}"
        route = create_optimized_route(
            name=route_name,
            driver=user,
            delivery_date=datetime.date.today(),
            order_ids=order_ids
        )
        
        credentials.append({
            'Driver Username': username,
            'Password': password,
            'Route ID': str(route.id),
            'Route Name': route_name,
            'City': 'Nagpur',
            'URL': f'http://nagpur.13.235.143.251.nip.io:8083/api/erp/orders/driver/{route.id}/start-trip/'
        })
        print(f"Set up {username} with {len(order_ids)} customers and Route: {route.id}")

# 4. Save to CSV
csv_file = 'vm_test_credentials.csv'
if credentials:
    keys = credentials[0].keys()
    with open(csv_file, 'w', newline='') as f:
        dict_writer = csv.DictWriter(f, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(credentials)

print(f"\n--- SETUP COMPLETE ---")
print(f"Credentials saved to: {os.path.abspath(csv_file)}")
print("You can now download this file and share it with your 7 drivers.")
