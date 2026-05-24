import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django_tenants.utils import schema_context
from tenants.models import City
from routing.models import Route as RoutingRoute, Driver, Zone
from inventory.models import Warehouse
from crm.models import Customer
from django.contrib.auth import get_user_model
import datetime

print("="*60)
print("RUNNING LOGISTICS & WAREHOUSE-DRIVER ROUTE INTEGRATION VALIDATION")
print("="*60)

with schema_context('pench-nagpur'):
    # Check current setup
    drivers = list(Driver.objects.all())
    warehouses = list(Warehouse.objects.all())
    zones = list(Zone.objects.all())
    customers = list(Customer.objects.all())
    
    print(f"Warehouses: {len(warehouses)}")
    for w in warehouses:
        print(f"  Warehouse: {w.name} | Lat: {w.latitude} | Lng: {w.longitude}")
        
    print(f"Drivers: {len(drivers)}")
    for d in drivers:
        print(f"  Driver: {d.user.username} | Warehouse: {d.warehouse.name if d.warehouse else 'None'}")
        
    print(f"Zones: {len(zones)}")
    for z in zones:
        print(f"  Zone: {z.name} | Assigned User: {z.assigned_driver.username if z.assigned_driver else 'None'}")
        
    print(f"Customers: {len(customers)} | Customers with Zones: {Customer.objects.exclude(zone=None).count()}")
    
    # Ensure at least one warehouse exists with coordinates
    if not warehouses:
        print("Creating a test warehouse...")
        w = Warehouse.objects.create(
            name="Main Nagpur Hub",
            address="Nagpur Central, Maharashtra",
            latitude=21.1458,
            longitude=79.0882
        )
        warehouses = [w]
        
    warehouse = warehouses[0]
    if warehouse.latitude is None or warehouse.longitude is None:
        print(f"Setting test coordinates for warehouse '{warehouse.name}'...")
        warehouse.latitude = 21.1458
        warehouse.longitude = 79.0882
        warehouse.save(update_fields=['latitude', 'longitude'])
        
    # Ensure driver is associated with warehouse
    driver = drivers[0] if drivers else None
    if driver and not driver.warehouse:
        print(f"Associating driver '{driver.user.username}' with warehouse '{warehouse.name}'...")
        driver.warehouse = warehouse
        driver.save(update_fields=['warehouse'])
        
    # Ensure a zone is assigned to this driver's user
    zone = zones[0] if zones else None
    if zone and driver:
        print(f"Assigning zone '{zone.name}' to driver user '{driver.user.username}'...")
        zone.assigned_driver = driver.user
        zone.save(update_fields=['assigned_driver'])
        
    # Let's ensure there's at least one customer inside this zone with location and an order
    customer = customers[0] if customers else None
    if customer:
        if not customer.zone and zone:
            customer.zone = zone
            customer.save(update_fields=['zone'])
        print(f"Customer: {customer.name} | Zone: {customer.zone.name if customer.zone else 'None'} | Location: {customer.location}")
        
        # Ensure customer has coordinates
        if not customer.location:
            customer.location = {'longitude': 79.0900, 'latitude': 21.1500}
            customer.save(update_fields=['location'])
            
        # Create a pending order for today
        from orders.models import Order, OrderStatus, Route
        today = datetime.date.today()
        
        # Clean existing orders/routes for today first so we can run clean
        Order.objects.filter(scheduled_delivery_date=today).delete()
        Route.objects.filter(delivery_date=today).delete()
        
        order = Order.objects.create(
            customer=customer,
            scheduled_delivery_date=today,
            status=OrderStatus.PENDING,
            delivery_address=customer.address or "Test address",
            total=100.0
        )
        print(f"Created a test pending order: {order.id} for date {today}")
        
        # Trigger Route Generation!
        from orders.services.route_generator import generate_daily_routes_for_date
        print("Invoking generate_daily_routes_for_date...")
        summary = generate_daily_routes_for_date(today)
        print(f"Generation Summary: {summary}")
        
        # Check generated routes in DB!
        generated_routes = list(Route.objects.filter(delivery_date=today))
        print(f"Generated Routes Count: {len(generated_routes)}")
        for r in generated_routes:
            print(f"  Route ID: {r.id}")
            print(f"  Route Name: {r.name}")
            print(f"  Route Driver: {r.driver} (User: {r.driver.username})")
            print(f"  Route Stops Count: {r.stops.count()}")
            
            # Check geometry contains the warehouse start point!
            if r.geometry:
                print(f"  Route Start Coordinate: {r.geometry.coords[0]}")
                print(f"  Warehouse Coordinate: ({warehouse.longitude}, {warehouse.latitude})")
                
print("="*60)
