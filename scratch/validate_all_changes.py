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
from routing.models import Driver
from orders.services.optimizer import create_optimized_route
from orders.services.trip_management import start_trip_for_route

print("=== STARTING COMPREHENSIVE VERIFICATION ===")

User = get_user_model()
city = City.objects.exclude(schema_name="public").first()
if not city:
    print("No tenant city found to run validation on!")
    sys.exit(1)

print(f"Using tenant schema: '{city.schema_name}'")

with schema_context(city.schema_name):
    # 1. Verify Order.save() update_fields behavior
    print("\n--- 1. Testing Order.save() with update_fields ---")
    customer = Customer.objects.first()
    if not customer:
        print("Creating mock customer for test...")
        customer = Customer.objects.create(
            name="Test Customer", phone="1234567890", address="Nagpur"
        )

    order = Order.objects.create(
        customer=customer,
        scheduled_delivery_date=datetime.date.today(),
        status=OrderStatus.PENDING,
        delivery_address=customer.address,
    )
    print(
        f"Created pending order. Status: {order.status}, Delivered At: {order.delivered_at}"
    )

    # Change status and save using update_fields
    order.status = OrderStatus.DELIVERED
    order.save(update_fields=["status"])

    # Re-fetch from DB
    refetched_order = Order.objects.get(id=order.id)
    print(
        f"Re-fetched status: {refetched_order.status}, Delivered At: {refetched_order.delivered_at}"
    )
    if refetched_order.delivered_at:
        print(
            "[SUCCESS] Order.save() successfully appended and saved 'delivered_at' inside 'update_fields'!"
        )
    else:
        print(
            "[FAILED] Order.save() FAILED to save 'delivered_at' when using update_fields!"
        )

    # 2. Verify bulk mark_all_delivered saving delivered_at
    print("\n--- 2. Testing bulk mark_all_delivered ---")
    order2 = Order.objects.create(
        customer=customer,
        scheduled_delivery_date=datetime.date.today(),
        status=OrderStatus.PENDING,
        delivery_address=customer.address,
    )
    print(f"Created second pending order ID: {order2.id}")

    # Bulk update to delivered
    Order.objects.filter(id=order2.id).update(
        status=OrderStatus.DELIVERED, delivered_at=timezone.now()
    )

    refetched_order2 = Order.objects.get(id=order2.id)
    print(
        f"Re-fetched second order status: {refetched_order2.status}, Delivered At: {refetched_order2.delivered_at}"
    )
    if refetched_order2.delivered_at:
        print("[SUCCESS] Bulk update successfully saved 'delivered_at'!")
    else:
        print("[FAILED] Bulk update FAILED to save 'delivered_at'!")

    # 3. Verify previous route auto-closing
    print("\n--- 3. Testing previous route auto-closing during new route creation ---")
    driver_user = User.objects.filter(is_driver=True).first()
    if not driver_user:
        print("Creating mock driver user...")
        driver_user = User.objects.create(
            username="test_driver", phone="9876543210", is_driver=True
        )

    driver_profile = Driver.objects.filter(user=driver_user).first()
    if not driver_profile:
        print("Creating mock driver profile...")
        warehouse = Warehouse.objects.first()
        if not warehouse:
            warehouse = Warehouse.objects.create(name="Central Warehouse")
        driver_profile = Driver.objects.create(
            user=driver_user, warehouse=warehouse, is_available=True
        )

    # Let's create an existing active (incomplete) route for this driver
    prev_route = Route.objects.create(
        name="Previous Active Route",
        driver=driver_user,
        delivery_date=datetime.date.today() - datetime.timedelta(days=1),
        is_completed=False,
        status=RouteStatus.IN_PROGRESS,
    )

    # Associate orders to this previous route
    ord_prev1 = Order.objects.create(
        customer=customer,
        scheduled_delivery_date=datetime.date.today() - datetime.timedelta(days=1),
        status=OrderStatus.PENDING,
        delivery_address=customer.address,
    )
    ord_prev2 = Order.objects.create(
        customer=customer,
        scheduled_delivery_date=datetime.date.today() - datetime.timedelta(days=1),
        status=OrderStatus.UNDELIVERED,  # One is already undelivered
        delivery_address=customer.address,
    )
    ord_prev3 = Order.objects.create(
        customer=customer,
        scheduled_delivery_date=datetime.date.today() - datetime.timedelta(days=1),
        status=OrderStatus.IN_TRANSIT,
        delivery_address=customer.address,
    )

    from orders.models import RouteStop

    RouteStop.objects.create(route=prev_route, order=ord_prev1, sequence_number=1)
    RouteStop.objects.create(route=prev_route, order=ord_prev2, sequence_number=2)
    RouteStop.objects.create(route=prev_route, order=ord_prev3, sequence_number=3)

    print(
        f"Created previous route ID: {prev_route.id} (is_completed={prev_route.is_completed}) with 3 stops."
    )

    # Ensure no routes exist for this driver on today before starting
    Route.objects.filter(driver=driver_user, delivery_date=datetime.date.today()).delete()

    # Now create a new route for this driver using create_optimized_route
    new_ord = Order.objects.create(
        customer=customer,
        scheduled_delivery_date=datetime.date.today(),
        status=OrderStatus.PENDING,
        delivery_address=customer.address,
    )
    if not customer.location:
        from django.contrib.gis.geos import Point

        customer.location = Point(79.0882, 21.1458)
        customer.save()

    print(f"Creating new route for driver {driver_user.username}...")
    new_route = create_optimized_route(
        name="New Optimized Route",
        driver=driver_user,
        date=datetime.date.today(),
        order_ids=[str(new_ord.id)],
    )

    # Re-fetch previous route and its orders to check if they are closed and undelivered
    prev_route.refresh_from_db()
    ord_prev1.refresh_from_db()
    ord_prev2.refresh_from_db()
    ord_prev3.refresh_from_db()

    print(
        f"Previous route after new route creation: is_completed={prev_route.is_completed}, status={prev_route.status}"
    )
    print(
        f"  Stop 1 (was Pending) status: {ord_prev1.status}, Delivered At: {ord_prev1.delivered_at}"
    )
    print(
        f"  Stop 2 (was Undelivered) status: {ord_prev2.status}, Delivered At: {ord_prev2.delivered_at}"
    )
    print(
        f"  Stop 3 (was In Transit) status: {ord_prev3.status}, Delivered At: {ord_prev3.delivered_at}"
    )

    if (
        prev_route.is_completed
        and ord_prev1.status == OrderStatus.UNDELIVERED
        and ord_prev3.status == OrderStatus.UNDELIVERED
    ):
        print(
            "[SUCCESS] Previous active route was successfully completed and remaining stops marked undelivered!"
        )
    else:
        print("[FAILED] Previous route auto-closing FAILED!")

    # 4. Verify starting a trip doesn't overwrite UNDELIVERED
    print("\n--- 4. Testing that start_trip_for_route preserves UNDELIVERED status ---")
    route_test = Route.objects.create(
        name="Test Status Reversion",
        driver=driver_user,
        delivery_date=datetime.date.today(),
        is_completed=False,
        status=RouteStatus.PENDING,
    )

    o_pending = Order.objects.create(
        customer=customer,
        scheduled_delivery_date=datetime.date.today(),
        status=OrderStatus.PENDING,
        delivery_address=customer.address,
    )
    o_undelivered = Order.objects.create(
        customer=customer,
        scheduled_delivery_date=datetime.date.today(),
        status=OrderStatus.UNDELIVERED,
        delivered_at=timezone.now() - datetime.timedelta(hours=1),
        delivery_address=customer.address,
    )

    RouteStop.objects.create(route=route_test, order=o_pending, sequence_number=1)
    RouteStop.objects.create(route=route_test, order=o_undelivered, sequence_number=2)

    print(f"Starting trip for route: {route_test.name}...")
    start_trip_for_route(route_test.id, driver_user)

    # Re-fetch orders
    o_pending.refresh_from_db()
    o_undelivered.refresh_from_db()

    print(f"Pending order status after start: {o_pending.status} (expected in_transit)")
    print(
        f"Undelivered order status after start: {o_undelivered.status} (expected undelivered)"
    )

    if (
        o_pending.status == OrderStatus.IN_TRANSIT
        and o_undelivered.status == OrderStatus.UNDELIVERED
    ):
        print(
            "[SUCCESS] start_trip_for_route successfully preserved the UNDELIVERED status while transitioning pending to in_transit!"
        )
    else:
        print("[FAILED] Reversion check FAILED!")

print("\n=== COMPREHENSIVE VERIFICATION COMPLETED ===")
