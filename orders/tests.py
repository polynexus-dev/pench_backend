from django_tenants.test.cases import TenantTestCase
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
