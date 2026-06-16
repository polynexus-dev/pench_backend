import os
import django
import sys
import datetime

sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection, transaction
from django_tenants.utils import schema_context
from django.utils import timezone
from django.contrib.auth import get_user_model

from tenants.models import City
from crm.models import Customer
from orders.models import Order, OrderStatus, Route, RouteStatus, RouteStop
from inventory.models import Product, Warehouse
from routing.models import Driver, Zone
from orders.services.route_generator import generate_daily_routes_for_date
from orders.services.optimizer import create_optimized_route

print("=== REPRODUCING ROUTE GENERATION BUG ===")

User = get_user_model()
city = City.objects.exclude(schema_name="public").first()
if not city:
    print("No tenant city found!")
    sys.exit(1)

print(f"Using tenant: {city.schema_name}")

with schema_context(city.schema_name):
    # 1. Clean up existing routes/orders/customers to have a clean slate
    RouteStop.objects.all().delete()
    Route.objects.all().delete()
    Order.objects.all().delete()
    from subscriptions.models import Subscription, SubscriptionItem
    from finance.models import MonthlyBill
    SubscriptionItem.objects.all().delete()
    Subscription.objects.all().delete()
    MonthlyBill.objects.all().delete()
    Customer.objects.all().delete()
    
    # 2. Setup Warehouse, Driver, Zone, Customers
    warehouse = Warehouse.objects.first()
    if not warehouse:
        warehouse = Warehouse.objects.create(name="Nagpur Warehouse", latitude=21.1458, longitude=79.0882)
    else:
        warehouse.latitude = 21.1458
        warehouse.longitude = 79.0882
        warehouse.save()

    driver_user = User.objects.filter(is_driver=True).first()
    if not driver_user:
        driver_user = User.objects.create(username="driver_bug_test", phone="9998887776", is_driver=True)
    
    driver_profile = Driver.objects.filter(user=driver_user).first()
    if not driver_profile:
        driver_profile = Driver.objects.create(user=driver_user, warehouse=warehouse, is_available=True)
    else:
        driver_profile.warehouse = warehouse
        driver_profile.is_available = True
        driver_profile.save()

    zone = Zone.objects.first()
    if not zone:
        zone = Zone.objects.create(name="North Nagpur", assigned_driver=driver_user, is_active=True)
    else:
        zone.assigned_driver = driver_user
        zone.is_active = True
        zone.save()

    # Create Customer 1
    from django.contrib.gis.geos import Point
    cust1 = Customer.objects.create(
        name="Customer One",
        phone="1111111111",
        email="cust1@example.com",
        address="Nagpur Stop 1",
        zone=zone,
        location=Point(79.0882, 21.1458)
    )

    # Create a subscription for Customer 1
    from subscriptions.models import Subscription, SubscriptionStatus, SubscriptionItem, DeliveryFrequency
    sub1 = Subscription.objects.create(
        customer=cust1,
        status=SubscriptionStatus.ACTIVE,
        start_date=datetime.date.today(),
        frequency=DeliveryFrequency.DAILY,
        delivery_address="Nagpur Stop 1"
    )
    product = Product.objects.first()
    if not product:
        product = Product.objects.create(name="Milk 1L", unit_price=60.00, unit="Liter", is_active=True)
    else:
        product.is_active = True
        product.save()

    SubscriptionItem.objects.create(subscription=sub1, product=product, quantity=1)

    print("Setup done. Running daily route generation for today...")
    today = datetime.date.today()
    
    res1 = generate_daily_routes_for_date(today)
    print("Generation 1 results:", res1)
    
    routes = list(Route.objects.filter(delivery_date=today))
    print(f"Routes in DB: {len(routes)}")
    for r in routes:
        print(f"  Route: ID={r.id}, Name='{r.name}', Status={r.status}, Stops Count={r.stops.count()}")

    print("\n--- Creating a second customer and subscription ---")
    cust2 = Customer.objects.create(
        name="Customer Two",
        phone="2222222222",
        email="cust2@example.com",
        address="Nagpur Stop 2",
        zone=zone,
        location=Point(79.0900, 21.1500)
    )
    sub2 = Subscription.objects.create(
        customer=cust2,
        status=SubscriptionStatus.ACTIVE,
        start_date=datetime.date.today(),
        frequency=DeliveryFrequency.DAILY,
        delivery_address="Nagpur Stop 2"
    )
    SubscriptionItem.objects.create(subscription=sub2, product=product, quantity=2)

    print("Running daily route generation again for today...")
    res2 = generate_daily_routes_for_date(today)
    print("Generation 2 results:", res2)

    routes2 = list(Route.objects.filter(delivery_date=today))
    print(f"Routes in DB now: {len(routes2)}")
    for r in routes2:
        print(f"  Route: ID={r.id}, Name='{r.name}', Status={r.status}, Stops Count={r.stops.count()}")

    print("\n--- Testing call with string date and driver profile (simulating View Actions) ---")
    # Clean slate again
    RouteStop.objects.all().delete()
    Route.objects.all().delete()
    Order.objects.all().delete()
    
    # Create order 1
    ord1 = Order.objects.create(
        customer=cust1,
        scheduled_delivery_date=today,
        status=OrderStatus.PENDING,
        delivery_address=cust1.address
    )
    
    # Create route via create_optimized_route with string date
    route_str_date = today.isoformat()
    print(f"Creating route for date string: '{route_str_date}'")
    r1 = create_optimized_route(
        name="Route 1",
        driver=driver_profile,
        date=route_str_date,
        order_ids=[str(ord1.id)]
    )
    print(f"Route 1 created: ID={r1.id}, Name='{r1.name}', Stops Count={r1.stops.count()}")
    
    # Create order 2
    ord2 = Order.objects.create(
        customer=cust2,
        scheduled_delivery_date=today,
        status=OrderStatus.PENDING,
        delivery_address=cust2.address
    )
    
    # Call create_optimized_route again with both orders (to update in-place)
    print(f"Creating route again with string date and both orders: '{[str(ord1.id), str(ord2.id)]}'")
    r2 = create_optimized_route(
        name="Route 1 Updated",
        driver=driver_profile,
        date=route_str_date,
        order_ids=[str(ord1.id), str(ord2.id)]
    )
    print(f"Route after second call: ID={r2.id}, Name='{r2.name}', Stops Count={r2.stops.count()}")
    
    routes_final = list(Route.objects.filter(delivery_date=today))
    print(f"Total routes in DB: {len(routes_final)}")
    for r in routes_final:
        print(f"  Route: ID={r.id}, Name='{r.name}', Status={r.status}, Stops Count={r.stops.count()}")

    print("\n--- Testing RouteViewSet.refresh_and_merge action ---")
    # Clean slate again
    RouteStop.objects.all().delete()
    Route.objects.all().delete()
    Order.objects.all().delete()
    
    # Remove cust3 if exists to avoid unique constraint violations
    Customer.objects.filter(email="cust3@example.com").delete()

    # 1. Create 2 separate routes manually for driver_user (pratham) for today
    ord_m1 = Order.objects.create(
        customer=cust1, scheduled_delivery_date=today, status=OrderStatus.UNDELIVERED, delivery_address=cust1.address
    )
    ord_m2 = Order.objects.create(
        customer=cust2, scheduled_delivery_date=today, status=OrderStatus.PENDING, delivery_address=cust2.address
    )
    
    route_dup1 = Route.objects.create(
        name="Route Duplicate 1",
        driver=driver_user,
        delivery_date=today,
        is_completed=True,
        status="completed",
    )
    RouteStop.objects.create(route=route_dup1, order=ord_m1, sequence_number=1)
    
    route_dup2 = Route.objects.create(
        name="Route Duplicate 2",
        driver=driver_user,
        delivery_date=today,
        is_completed=False,
        status="pending",
    )
    RouteStop.objects.create(route=route_dup2, order=ord_m2, sequence_number=1)
    
    print(f"Created 2 separate routes for {driver_user.username}:")
    print(f"  Route 1: ID={route_dup1.id}, Stops Count={route_dup1.stops.count()}")
    print(f"  Route 2: ID={route_dup2.id}, Stops Count={route_dup2.stops.count()}")
    
    # 2. Create an unassigned order for a new customer
    cust3 = Customer.objects.create(
        name="Customer Three",
        phone="3333333333",
        email="cust3@example.com",
        address="Nagpur Stop 3",
        zone=zone,
        location=Point(79.0950, 21.1600)
    )
    ord_unassigned = Order.objects.create(
        customer=cust3,
        scheduled_delivery_date=today,
        status=OrderStatus.PENDING,
        delivery_address=cust3.address
    )
    print(f"Created unassigned order ID: {ord_unassigned.id} for new customer in same zone.")
    
    # 3. Invoke refresh_and_merge action
    from orders.views import RouteViewSet
    from rest_framework.test import APIRequestFactory
    
    factory = APIRequestFactory()
    request_obj = factory.post("/api/routes/refresh-and-merge/", {"date": today.isoformat()}, format="json")
    # Authenticate request to pass permissions
    driver_user.is_superuser = True
    driver_user.is_erp_user = True
    driver_user.save()
    request_obj.user = driver_user
    
    # Instantiate view
    view = RouteViewSet.as_view({"post": "refresh_and_merge"})
    response = view(request_obj)
    
    print(f"Response Status: {response.status_code}")
    print(f"Response Data: {response.data}")
    
    # Re-fetch routes
    routes_after = list(Route.objects.filter(delivery_date=today))
    print(f"Total routes in DB after refresh-and-merge: {len(routes_after)}")
    for r in routes_after:
        print(f"  Route: ID={r.id}, Name='{r.name}', Status={r.status}, Stops Count={r.stops.count()}")
        print(f"  Stops:")
        for s in r.stops.all():
            print(f"    - Stop {s.sequence_number}: Order ID={s.order_id}, Customer={s.order.customer.name}")



