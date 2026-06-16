from unittest.mock import patch
from django_tenants.test.cases import TenantTestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from tracking.models import DriverLocation, DriverTrail, HAS_GIS
from routing.models import Driver
import datetime

try:
    from django.contrib.gis.geos import Point
except ImportError:
    Point = None


class TestDriverLocationTrail(TenantTestCase):
    """Unit tests for the DriverLocationViewSet.trail endpoint and serializer."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test City"
        tenant.state = "Test State"
        tenant.code = "TST"
        tenant.create_schema(sync_schema=True)

    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.driver_user = User.objects.create_user(
            username="test_driver_tracking",
            email="driver_tracking@example.com",
            password="testpassword",
            is_driver=True,
            is_staff=True,
            is_erp_user=True,
            tenant_schema="test",
        )

        self.driver_profile, _ = Driver.objects.get_or_create(
            user=self.driver_user,
            defaults={
                "vehicle_plate": "TEST-1111",
                "is_available": True,
                "on_trip": False,
            },
        )
        self.driver_profile.vehicle_plate = "TEST-1111"
        self.driver_profile.is_available = True
        self.driver_profile.on_trip = False
        self.driver_profile.save()

        if HAS_GIS and Point:
            location_data = Point(79.0, 21.0, srid=4326)
        else:
            location_data = {"lat": 21.0, "lng": 79.0}

        # Create live location for driver
        self.location_obj = DriverLocation.objects.create(
            user=self.driver_user, location=location_data
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.driver_user)

    @patch("routing.services.osrm_client.match_trail")
    def test_trail_empty(self, mock_match_trail):
        url = f"/api/erp/tracking/live/{self.location_obj.id}/trail/"
        response = self.client.get(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["type"], "Feature")
        self.assertIsNone(response.data["geometry"])
        self.assertEqual(response.data["properties"]["distance_km"], 0.0)

    @patch("routing.services.osrm_client.match_trail")
    def test_trail_single_point(self, mock_match_trail):
        if HAS_GIS and Point:
            location_data = Point(79.0, 21.0, srid=4326)
        else:
            location_data = {"lat": 21.0, "lng": 79.0}

        # Create a single trail record
        DriverTrail.objects.create(
            user=self.driver_user,
            location=location_data,
            cleaned_location=location_data,
        )

        url = f"/api/erp/tracking/live/{self.location_obj.id}/trail/"
        response = self.client.get(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["geometry"]["type"], "Point")
        self.assertEqual(response.data["geometry"]["coordinates"], [79.0, 21.0])
        self.assertEqual(response.data["properties"]["distance_km"], 0.0)

    @patch("routing.services.osrm_client.match_trail")
    def test_trail_multiple_points_linestring(self, mock_match_trail):
        # Mock OSRM matched road coordinates
        mock_match_trail.return_value = [[79.0, 21.0], [79.01, 21.01], [79.02, 21.02]]

        if HAS_GIS and Point:
            p1 = Point(79.0, 21.0, srid=4326)
            p2 = Point(79.02, 21.02, srid=4326)
        else:
            p1 = {"lat": 21.0, "lng": 79.0}
            p2 = {"lat": 21.02, "lng": 79.02}

        # Create multiple trail records
        DriverTrail.objects.create(
            user=self.driver_user,
            location=p1,
            cleaned_location=p1,
            timestamp=datetime.datetime.now() - datetime.timedelta(minutes=10),
        )

        # Second point after 6 minutes
        DriverTrail.objects.create(
            user=self.driver_user,
            location=p2,
            cleaned_location=p2,
            timestamp=datetime.datetime.now(),
        )

        url = f"/api/erp/tracking/live/{self.location_obj.id}/trail/"
        response = self.client.get(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)

        # Verify it returns a LineString, not MultiLineString
        self.assertEqual(response.data["geometry"]["type"], "LineString")
        self.assertEqual(
            response.data["geometry"]["coordinates"],
            [[79.0, 21.0], [79.01, 21.01], [79.02, 21.02]],
        )

        # Verify distance is calculated and is > 0.0
        self.assertGreater(response.data["properties"]["distance_km"], 0.0)


class TestTrackingProximityAlert(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test City"
        tenant.state = "Test State"
        tenant.code = "TST"
        tenant.create_schema(sync_schema=True)

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)
        User = get_user_model()
        
        # Create driver
        self.driver_user = User.objects.create_user(
            username="driver_proximity",
            email="driver_prox@example.com",
            password="testpassword",
            is_driver=True,
            tenant_schema="test",
        )
        self.driver_profile, _ = Driver.objects.get_or_create(
            user=self.driver_user,
            defaults={
                "vehicle_plate": "TEST-PROX",
                "is_available": True,
                "on_trip": True,
            },
        )
        
        # Create customer user and profile
        self.cust_user = User.objects.create_user(
            username="cust_proximity",
            email="cust_prox@example.com",
            password="testpassword",
            is_customer=True,
            tenant_schema="test",
        )
        
        # We need a location within 250m and a location outside 250m.
        # Driver will update to lat 21.0, lng 79.0.
        # Inside target coordinate: lat 21.001, lng 79.001.
        # Outside target coordinate: lat 21.01, lng 79.01.
        from crm.models import Customer
        if HAS_GIS and Point:
            loc_near = Point(79.001, 21.001)
            loc_far = Point(79.01, 21.01)
        else:
            loc_near = {"longitude": 79.001, "latitude": 21.001}
            loc_far = {"longitude": 79.01, "latitude": 21.01}

        self.customer_near = Customer.objects.get(user=self.cust_user)
        self.customer_near.name = "Near Customer"
        self.customer_near.email = "near@example.com"
        self.customer_near.location = loc_near
        self.customer_near.is_active = True
        self.customer_near.save()
        
        self.cust_user_far = User.objects.create_user(
            username="cust_far",
            email="cust_far@example.com",
            password="testpassword",
            is_customer=True,
            tenant_schema="test",
        )
        self.customer_far = Customer.objects.get(user=self.cust_user_far)
        self.customer_far.name = "Far Customer"
        self.customer_far.email = "far@example.com"
        self.customer_far.location = loc_far
        self.customer_far.is_active = True
        self.customer_far.save()
        
        # Create route stop and orders
        from orders.models import Route as OrdersRoute, Order, RouteStop, OrderStatus
        import datetime
        self.orders_route = OrdersRoute.objects.create(
            name="Test Proximity Route",
            driver=self.driver_user,
            delivery_date=datetime.date.today(),
            is_completed=False,
        )
        
        self.order_near = Order.objects.create(
            customer=self.customer_near,
            scheduled_delivery_date=datetime.date.today(),
            delivery_address="Near St",
            status=OrderStatus.PENDING,
            arriving_notification_sent=False,
        )
        
        self.order_far = Order.objects.create(
            customer=self.customer_far,
            scheduled_delivery_date=datetime.date.today(),
            delivery_address="Far St",
            status=OrderStatus.PENDING,
            arriving_notification_sent=False,
        )
        
        RouteStop.objects.create(
            route=self.orders_route,
            order=self.order_near,
            sequence_number=1,
        )
        RouteStop.objects.create(
            route=self.orders_route,
            order=self.order_far,
            sequence_number=2,
        )

    @patch("notifications.services.send_push_notification")
    @patch("routing.services.osrm_client.snap_to_road")
    @patch("routing.services.osrm_client.match_trail")
    def test_proximity_notification_sent(self, mock_match, mock_snap, mock_send):
        # Driver reports position at (79.0, 21.0)
        # Mock snap_to_road to return the same coordinate so it doesn't try to query actual OSRM API
        mock_snap.return_value = (79.0, 21.0)
        mock_match.return_value = [[79.0, 21.0]]
        
        from tracking.consumers import TrackingConsumer
        from asgiref.sync import async_to_sync
        
        consumer = TrackingConsumer()
        consumer.user = self.driver_user
        consumer.tenant = self.tenant
        
        # Execute the update
        consumer.update_driver_location.func.__self__.func(consumer, 21.0, 79.0, accuracy=10.0)
        
        # Refresh order records
        self.order_near.refresh_from_db()
        self.order_far.refresh_from_db()
        
        # Assertions
        # Near order must have notification set to True
        self.assertTrue(self.order_near.arriving_notification_sent)
        # Far order must have notification set to False
        self.assertFalse(self.order_far.arriving_notification_sent)
        
        # Verify send_push_notification was called once with near customer user
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        self.assertEqual(kwargs["user"], self.cust_user)
        self.assertIn("arriving shortly", kwargs["body"])
        self.assertEqual(kwargs["order"], self.order_near)
