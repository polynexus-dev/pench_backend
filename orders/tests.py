from django_tenants.test.cases import TenantTestCase
from django.test import override_settings
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from crm.models import Customer
from subscriptions.models import Subscription, DeliveryFrequency, SubscriptionStatus
from inventory.models import Product, Warehouse, Stock, RawMaterial, BottleType
from orders.models import Order, Route, RouteStop
from tracking.models import HAS_GIS
import datetime

try:
    from django.contrib.gis.geos import Point
except ImportError:
    Point = None



class TestRouteManualControl(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test City"
        tenant.state = "Test State"
        tenant.code = "TST"
        tenant.create_schema(sync_schema=True)

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        User = get_user_model()

        # Create ERP manager
        self.manager_user = User.objects.create_user(
            username="orders_manager",
            email="manager@example.com",
            password="testpassword",
            is_erp_user=True,
            tenant_schema="test",
        )
        # Assign to Logistics_Managers group
        logistics_group, _ = Group.objects.get_or_create(name="Logistics_Managers")
        self.manager_user.groups.add(logistics_group)

        self.client = APIClient()
        self.client.force_authenticate(user=self.manager_user)

        # Set up zone and driver
        from routing.models import Zone, Driver
        self.driver_user = User.objects.create_user(
            username="route_driver",
            email="driver@example.com",
            password="testpassword",
            is_driver=True,
            tenant_schema="test",
        )
        self.driver_profile, _ = Driver.objects.get_or_create(
            user=self.driver_user,
            defaults={
                "vehicle_plate": "TST-ROUTE",
                "is_available": True,
            }
        )
        
        self.zone = Zone.objects.create(
            name="Test Route Zone",
            assigned_driver=self.driver_user
        )

        # Create warehouse and link to driver
        self.warehouse = Warehouse.objects.create(
            name="Manual Depot",
            latitude=21.0,
            longitude=79.0,
            is_active=True
        )
        self.driver_profile.warehouse = self.warehouse
        self.driver_profile.save()

        # Create customer profile
        if HAS_GIS and Point:
            loc = Point(79.001, 21.001)
        else:
            loc = {"longitude": 79.001, "latitude": 21.001}

        self.customer = Customer.objects.create(
            name="Manual Customer",
            email="cust_man@example.com",
            zone=self.zone,
            is_new=False,
            location=loc
        )

        # Create a subscription
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            status=SubscriptionStatus.ACTIVE,
            frequency=DeliveryFrequency.DAILY,
            start_date=datetime.date.today(),
        )
        self.product = Product.objects.create(
            name="Milk 1L",
            sku="MILK-1L",
            unit_price=60.0,
            is_active=True,
        )
        from subscriptions.models import SubscriptionItem
        SubscriptionItem.objects.create(
            subscription=self.subscription,
            product=self.product,
            quantity=2,
        )

    def test_trigger_and_clear_daily_generation(self):
        target_date_str = str(datetime.date.today() + datetime.timedelta(days=1))
        
        # 1. Trigger generation
        url_trigger = "/api/erp/orders/routes/trigger-daily-generation/"
        response = self.client.post(url_trigger, {"date": target_date_str}, format="json", HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)
        self.assertIn("summary", response.data)
        self.assertEqual(response.data["summary"]["orders_created"], 1)
        self.assertEqual(response.data["summary"]["routes_created"], 1)

        # Verify database objects
        self.assertTrue(Order.objects.filter(scheduled_delivery_date=target_date_str).exists())
        self.assertTrue(Route.objects.filter(delivery_date=target_date_str).exists())
        self.assertTrue(RouteStop.objects.filter(route__delivery_date=target_date_str).exists())

        # 2. Clear generation
        url_clear = "/api/erp/orders/routes/clear-daily-generation/"
        response = self.client.post(url_clear, {"date": target_date_str}, format="json", HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)
        self.assertIn("details", response.data)
        self.assertEqual(response.data["details"]["deleted_routes"], 1)
        self.assertGreaterEqual(response.data["details"]["deleted_subscription_orders"], 1)

        # Verify database objects are deleted
        self.assertFalse(Order.objects.filter(scheduled_delivery_date=target_date_str).exists())
        self.assertFalse(Route.objects.filter(delivery_date=target_date_str).exists())
        self.assertFalse(RouteStop.objects.filter(route__delivery_date=target_date_str).exists())

    def test_control_panel_view(self):
        url = "/api/erp/orders/routes/control-panel/"
        response = self.client.get(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Pench Route Control Center", response.content)

    def test_route_stop_serializer_bottle_fields(self):
        # 1. Create a bottle type
        bottle_type = BottleType.objects.create(name="1L returnable bottle", volume_ml=1000)
        
        # 2. Make the product returnable and link the bottle type
        self.product.is_returnable = True
        self.product.bottle_type = bottle_type
        self.product.save()

        # 3. Set a bottle balance for the customer
        from inventory.models import CustomerBottleBalance
        CustomerBottleBalance.objects.create(
            customer=self.customer,
            bottle_type=bottle_type,
            balance=5
        )

        # 4. Trigger route generation to get a RouteStop
        target_date_str = str(datetime.date.today() + datetime.timedelta(days=1))
        url_trigger = "/api/erp/orders/routes/trigger-daily-generation/"
        response = self.client.post(url_trigger, {"date": target_date_str}, format="json", HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)

        # 5. Retrieve route details and check stop serializer fields
        route = Route.objects.get(delivery_date=target_date_str)
        url_route = f"/api/erp/orders/routes/{route.id}/"
        response_route = self.client.get(url_route, HTTP_HOST="tenant.test.com")
        self.assertEqual(response_route.status_code, 200)

        stops = response_route.data["stops"]
        self.assertEqual(len(stops), 1)
        stop = stops[0]

        # Verify bottles_to_deliver and bottles_to_take_back
        self.assertIn("bottles_to_deliver", stop)
        self.assertIn("bottles_to_take_back", stop)
        
        # Bottles to deliver: we had 2 quantity in subscription items
        self.assertEqual(len(stop["bottles_to_deliver"]), 1)
        self.assertEqual(stop["bottles_to_deliver"][0]["bottle_type_name"], "1L returnable bottle")
        self.assertEqual(stop["bottles_to_deliver"][0]["quantity"], 2)
        self.assertEqual(stop["bottles_to_deliver"][0]["value"], 1.0)

        # Bottles to take back: balance was 5
        self.assertEqual(len(stop["bottles_to_take_back"]), 1)
        self.assertEqual(stop["bottles_to_take_back"][0]["bottle_type_name"], "1L returnable bottle")
        self.assertEqual(stop["bottles_to_take_back"][0]["quantity"], 5)
        self.assertEqual(stop["bottles_to_take_back"][0]["value"], 1.0)

        # Verify new customer flag
        self.assertIn("is_new_customer", stop)
        self.assertFalse(stop["is_new_customer"])

    def test_route_generation_does_not_close_today_route(self):
        from django.utils import timezone
        from orders.services.optimizer import create_optimized_route
        from orders.models import OrderStatus

        # 1. Create a route for today (delivery_date = today)
        today = timezone.localdate()
        today_route = Route.objects.create(
            name="Today Route",
            driver=self.driver_user,
            delivery_date=today,
            is_completed=False,
        )

        # 2. Run route generation/optimization for tomorrow
        tomorrow = today + datetime.timedelta(days=1)
        tomorrow_order = Order.objects.create(
            customer=self.customer,
            scheduled_delivery_date=tomorrow,
            status=OrderStatus.PENDING,
            delivery_address=self.customer.address,
        )
        
        # Optimize route for tomorrow
        tomorrow_route = create_optimized_route(
            name="Tomorrow Route",
            driver=self.driver_user,
            date=tomorrow,
            order_ids=[str(tomorrow_order.id)],
        )

        # 3. Verify that today's route was NOT auto-completed
        today_route.refresh_from_db()
        self.assertFalse(today_route.is_completed)
        self.assertNotEqual(today_route.status, "completed")

        # 4. Verify that a past route (e.g. yesterday) IS auto-completed
        yesterday = today - datetime.timedelta(days=1)
        yesterday_route = Route.objects.create(
            name="Yesterday Route",
            driver=self.driver_user,
            delivery_date=yesterday,
            is_completed=False,
        )
        
        # Optimize route for a future date (e.g. tomorrow) again for the same driver,
        # but since tomorrow's route already exists, we must create a new one for a new day
        day_after_tomorrow = tomorrow + datetime.timedelta(days=1)
        future_order = Order.objects.create(
            customer=self.customer,
            scheduled_delivery_date=day_after_tomorrow,
            status=OrderStatus.PENDING,
            delivery_address=self.customer.address,
        )
        
        future_route = create_optimized_route(
            name="Future Route",
            driver=self.driver_user,
            date=day_after_tomorrow,
            order_ids=[str(future_order.id)],
        )
        
        yesterday_route.refresh_from_db()
        self.assertTrue(yesterday_route.is_completed)
        self.assertEqual(yesterday_route.status, "completed")

    def test_manual_trip_completion_disabled(self):
        from rest_framework import status
        # Create a route for today
        today = datetime.date.today()
        route = Route.objects.create(
            name="Today Route",
            driver=self.driver_user,
            delivery_date=today,
            is_completed=False,
        )

        # 1. Test complete-trip endpoint on DriverViewSet (Driver App)
        self.client.force_authenticate(user=self.driver_user)
        # Ensure driver user is in the Drivers group to bypass permissions
        drivers_group, _ = Group.objects.get_or_create(name="Drivers")
        self.driver_user.groups.add(drivers_group)

        res = self.client.post(f"/api/erp/orders/driver/stop-tracking/", HTTP_HOST="tenant.test.com")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Manual trip tracking completion is disabled", res.json()["error"])

        res = self.client.post(f"/api/erp/orders/driver/{route.id}/complete-trip/", HTTP_HOST="tenant.test.com")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Manual trip completion is disabled", res.json()["error"])

        # 2. Test RouteViewSet update and partial_update endpoints (Admin Dashboard)
        self.client.force_authenticate(user=self.manager_user)
        
        # Try to patch is_completed=True
        res = self.client.patch(f"/api/erp/orders/routes/{route.id}/", {"is_completed": True}, HTTP_HOST="tenant.test.com")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Manual trip completion is disabled", res.json()["error"])

        # Try to patch status=completed
        res = self.client.patch(f"/api/erp/orders/routes/{route.id}/", {"status": "completed"}, HTTP_HOST="tenant.test.com")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Manual trip completion is disabled", res.json()["error"])

    def test_route_metrics_calculation(self):
        from tracking.models import DriverTrail
        from orders.services.trip_management import update_route_metrics
        from django.utils import timezone
        
        # 1. Create a route
        route = Route.objects.create(
            name="Metrics Route",
            driver=self.driver_user,
            delivery_date=datetime.date.today(),
            is_completed=False,
        )
        
        # Add a RouteStop with customer location (79.001, 21.001) - distance from warehouse (79.0, 21.0) is about 150m
        order = Order.objects.create(
            customer=self.customer,
            scheduled_delivery_date=datetime.date.today(),
            status="pending",
            delivery_address=self.customer.address,
        )
        RouteStop.objects.create(
            route=route,
            order=order,
            sequence_number=1
        )
        
        # 2. Add some trail points
        base_time = timezone.now() - datetime.timedelta(hours=1)
        
        def create_trail(lon, lat, minutes_offset):
            from django.contrib.gis.geos import Point
            loc = Point(lon, lat) if (HAS_GIS and Point) else {"lng": lon, "lat": lat}
            trail = DriverTrail.objects.create(
                user=self.driver_user,
                route=None, # Fallback path queries by user & date
                location=loc,
                cleaned_location=loc
            )
            # Override auto_now_add using update
            DriverTrail.objects.filter(id=trail.id).update(timestamp=base_time + datetime.timedelta(minutes=minutes_offset))
        
        # 0 mins: at warehouse (79.0, 21.0)
        create_trail(79.0, 21.0, 0)
        
        # 5 mins: leaves warehouse, stops at customer (79.001, 21.001)
        # We will stay here for 15 minutes (from offset 5 to 20)
        create_trail(79.001, 21.001, 5)
        create_trail(79.001, 21.001, 10)
        create_trail(79.001, 21.001, 15)
        create_trail(79.001, 21.001, 20)
        
        # 25 mins: returns to warehouse (79.0, 21.0)
        create_trail(79.0, 21.0, 25)
        
        # 3. Call update_route_metrics
        update_route_metrics(route)
        route.refresh_from_db()
        
        # 4. Verify results
        # Time leaves at 5 mins, returns at 25 mins -> duration should be 20 mins
        self.assertEqual(route.actual_duration_minutes, 20)
        
        # Distance:
        # segment 1: (79.001, 21.001) to (79.001, 21.001) at 10, 15, 20 mins -> 0 distance
        # segment 2: (79.001, 21.001) to (79.0, 21.0) at 25 mins -> about 0.15 km
        # Let's verify actual_distance_km is around 0.15 km
        self.assertGreater(route.actual_distance_km, 0.0)
        self.assertLess(route.actual_distance_km, 0.5)
        
        # Stoppage time:
        # Stop at customer (79.001, 21.001) from offset 5 to 20 (15 mins total)
        # Customer is at (79.001, 21.001) which is 0m away, so N = 1 customer
        # Allowance = 2 * N = 2 mins
        # Unproductive stoppage = max(0, 15 - 2) = 13 mins
        # Let's assert stoppage_duration_minutes is around 13 mins
        self.assertEqual(route.stoppage_duration_minutes, 13)

        # Stoppage location history assertions:
        self.assertEqual(len(route.stoppage_history), 1)
        stop_entry = route.stoppage_history[0]
        self.assertAlmostEqual(stop_entry["lat"], 21.001)
        self.assertAlmostEqual(stop_entry["lng"], 79.001)
        self.assertEqual(stop_entry["duration_minutes"], 15.0)
        self.assertEqual(stop_entry["near_customers"], 1)
        self.assertEqual(stop_entry["allowance_minutes"], 2.0)
        self.assertEqual(stop_entry["unproductive_minutes"], 13.0)

    def test_broken_bottle_transaction_logic(self):
        from inventory.models import BottleType, CustomerBottleBalance, BottleTransactionType
        from inventory.services.bottle_service import record_bottle_transaction
        
        bottle_type = BottleType.objects.create(name="1L returnable bottle", volume_ml=1000)
        
        # Initialize customer balance to 5
        balance_obj = CustomerBottleBalance.objects.create(
            customer=self.customer,
            bottle_type=bottle_type,
            balance=5,
            broken_balance=0
        )
        
        # Record a broken transaction of quantity 2
        record_bottle_transaction(
            bottle_type=bottle_type,
            quantity=2,
            transaction_type=BottleTransactionType.BROKEN,
            customer=self.customer,
            user=self.manager_user
        )
        
        # Refresh from db
        balance_obj.refresh_from_db()
        
        # Verify balance was decremented (5 - 2 = 3)
        self.assertEqual(balance_obj.balance, 3)
        
        # Verify broken_balance was incremented (0 + 2 = 2)
        self.assertEqual(balance_obj.broken_balance, 2)



