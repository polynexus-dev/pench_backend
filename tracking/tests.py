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
        tenant.name = 'Test City'
        tenant.state = 'Test State'
        tenant.code = 'TST'

    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.driver_user = User.objects.create_user(
            username='test_driver_tracking',
            email='driver_tracking@example.com',
            password='testpassword',
            is_driver=True,
            is_staff=True,
            is_erp_user=True,
            tenant_schema='test'
        )
        
        self.driver_profile, _ = Driver.objects.get_or_create(
            user=self.driver_user,
            defaults={
                'vehicle_plate': 'TEST-1111',
                'is_available': True,
                'on_trip': False
            }
        )
        self.driver_profile.vehicle_plate = 'TEST-1111'
        self.driver_profile.is_available = True
        self.driver_profile.on_trip = False
        self.driver_profile.save()

        if HAS_GIS and Point:
            location_data = Point(79.0, 21.0, srid=4326)
        else:
            location_data = {'lat': 21.0, 'lng': 79.0}

        # Create live location for driver
        self.location_obj = DriverLocation.objects.create(
            user=self.driver_user,
            location=location_data
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.driver_user)

    @patch('routing.services.osrm_client.match_trail')
    def test_trail_empty(self, mock_match_trail):
        url = f'/api/erp/tracking/live/{self.location_obj.id}/trail/'
        response = self.client.get(url, HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['type'], 'Feature')
        self.assertIsNone(response.data['geometry'])
        self.assertEqual(response.data['properties']['distance_km'], 0.0)

    @patch('routing.services.osrm_client.match_trail')
    def test_trail_single_point(self, mock_match_trail):
        if HAS_GIS and Point:
            location_data = Point(79.0, 21.0, srid=4326)
        else:
            location_data = {'lat': 21.0, 'lng': 79.0}

        # Create a single trail record
        DriverTrail.objects.create(
            user=self.driver_user,
            location=location_data,
            cleaned_location=location_data
        )
        
        url = f'/api/erp/tracking/live/{self.location_obj.id}/trail/'
        response = self.client.get(url, HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['geometry']['type'], 'Point')
        self.assertEqual(response.data['geometry']['coordinates'], [79.0, 21.0])
        self.assertEqual(response.data['properties']['distance_km'], 0.0)

    @patch('routing.services.osrm_client.match_trail')
    def test_trail_multiple_points_linestring(self, mock_match_trail):
        # Mock OSRM matched road coordinates
        mock_match_trail.return_value = [
            [79.0, 21.0],
            [79.01, 21.01],
            [79.02, 21.02]
        ]
        
        if HAS_GIS and Point:
            p1 = Point(79.0, 21.0, srid=4326)
            p2 = Point(79.02, 21.02, srid=4326)
        else:
            p1 = {'lat': 21.0, 'lng': 79.0}
            p2 = {'lat': 21.02, 'lng': 79.02}

        # Create multiple trail records
        DriverTrail.objects.create(
            user=self.driver_user,
            location=p1,
            cleaned_location=p1,
            timestamp=datetime.datetime.now() - datetime.timedelta(minutes=10)
        )
        
        # Second point after 6 minutes
        DriverTrail.objects.create(
            user=self.driver_user,
            location=p2,
            cleaned_location=p2,
            timestamp=datetime.datetime.now()
        )

        url = f'/api/erp/tracking/live/{self.location_obj.id}/trail/'
        response = self.client.get(url, HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        
        # Verify it returns a LineString, not MultiLineString
        self.assertEqual(response.data['geometry']['type'], 'LineString')
        self.assertEqual(response.data['geometry']['coordinates'], [
            [79.0, 21.0],
            [79.01, 21.01],
            [79.02, 21.02]
        ])
        
        # Verify distance is calculated and is > 0.0
        self.assertGreater(response.data['properties']['distance_km'], 0.0)
