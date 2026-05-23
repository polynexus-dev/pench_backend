from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.conf import settings
from django.db import connection
from django.db.models.signals import pre_save, post_save
from routing.models import Zone
from crm.models import Customer, HAS_GIS, auto_assign_customer_zone, auto_assign_customers_on_zone_change

try:
    from django.contrib.gis.geos import Point, Polygon
except ImportError:
    Point = None
    Polygon = None


class CustomerAutoAssignZonesTestCase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test City'
        tenant.state = 'Test State'
        tenant.code = 'TST'
        tenant.create_schema(sync_schema=True)

    def setUp(self):
        super().setUp()
        
        # Disconnect signals during setUp so they don't interfere with manual endpoint tests
        pre_save.disconnect(auto_assign_customer_zone, sender=Customer)
        post_save.disconnect(auto_assign_customers_on_zone_change, sender=Zone)

        # Ensure we start in the tenant context
        connection.set_tenant(self.tenant)
        User = get_user_model()

        # Create authorized user (CRM Manager) with unique phone
        self.manager_user = User.objects.create_user(
            username='crm_manager',
            email='manager@example.com',
            password='testpassword',
            phone='9000000010',
            tenant_schema='test'
        )
        crm_group, _ = Group.objects.get_or_create(name='CRM_Managers')
        self.manager_user.groups.add(crm_group)

        # Create unauthorized user with unique phone
        self.regular_user = User.objects.create_user(
            username='regular_user',
            email='regular@example.com',
            password='testpassword',
            phone='9000000011',
            tenant_schema='test'
        )

        # Explicitly restore the tenant context after creating shared users
        connection.set_tenant(self.tenant)

        # Initialize API clients
        self.authorized_client = APIClient()
        self.authorized_client.force_authenticate(user=self.manager_user)

        self.unauthorized_client = APIClient()
        self.unauthorized_client.force_authenticate(user=self.regular_user)

        # Create a test zone
        # Boundaries: square from long 79.0 to 80.0, lat 21.0 to 22.0
        if HAS_GIS and Polygon:
            boundary = Polygon(((79.0, 21.0), (80.0, 21.0), (80.0, 22.0), (79.0, 22.0), (79.0, 21.0)))
        else:
            boundary = {
                "type": "Polygon",
                "coordinates": [
                    [[79.0, 21.0], [80.0, 21.0], [80.0, 22.0], [79.0, 22.0], [79.0, 21.0]]
                ]
            }

        self.zone = Zone.objects.create(
            name='Test Zone Central',
            description='Test delivery zone',
            boundary=boundary,
            is_active=True
        )

        # Create customer inside zone
        if HAS_GIS and Point:
            loc_inside = Point(79.5, 21.5)
        else:
            loc_inside = {"longitude": 79.5, "latitude": 21.5}

        self.customer_inside = Customer.objects.create(
            name='Customer Inside',
            email='inside@example.com',
            location=loc_inside,
            zone=None,
            is_active=True
        )

        # Create customer outside zone
        if HAS_GIS and Point:
            loc_outside = Point(78.5, 20.5)
        else:
            loc_outside = {"longitude": 78.5, "latitude": 20.5}

        self.customer_outside = Customer.objects.create(
            name='Customer Outside',
            email='outside@example.com',
            location=loc_outside,
            zone=None,
            is_active=True
        )

        # Create customer with no location
        self.customer_no_loc = Customer.objects.create(
            name='Customer No Location',
            email='noloc@example.com',
            location=None,
            zone=None,
            is_active=True
        )

        # Create inactive customer inside zone
        self.customer_inactive = Customer.objects.create(
            name='Customer Inactive',
            email='inactive@example.com',
            location=loc_inside,
            zone=None,
            is_active=False
        )

    def tearDown(self):
        # Make sure signals are reconnected after the tests
        pre_save.connect(auto_assign_customer_zone, sender=Customer)
        post_save.connect(auto_assign_customers_on_zone_change, sender=Zone)
        super().tearDown()

    def test_auto_assign_zones_success(self):
        """
        Verify that calling the endpoint assigns the correct zone to customers
        based on their location coordinates.
        """
        # Ensure we are in tenant context
        connection.set_tenant(self.tenant)
        url = '/api/erp/customers/auto-assign-zones/'
        response = self.authorized_client.post(url, {}, HTTP_HOST='tenant.test.com')

        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.data)
        self.assertEqual(response.data["scanned"], 2)  # Inside and Outside (active only)
        self.assertEqual(response.data["updated"], 1)  # Only inside customer should be updated

        # Refresh from DB and verify assignments
        self.customer_inside.refresh_from_db()
        self.customer_outside.refresh_from_db()
        self.customer_no_loc.refresh_from_db()
        self.customer_inactive.refresh_from_db()

        self.assertEqual(self.customer_inside.zone, self.zone)
        self.assertIsNone(self.customer_outside.zone)
        self.assertIsNone(self.customer_no_loc.zone)
        self.assertIsNone(self.customer_inactive.zone)

    def test_auto_assign_zones_unauthorized(self):
        """
        Verify that users without CRM_Managers or ERP_Admins permissions
        cannot execute the endpoint.
        """
        # Ensure we are in tenant context
        connection.set_tenant(self.tenant)
        url = '/api/erp/customers/auto-assign-zones/'
        response = self.unauthorized_client.post(url, {}, HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 403)

        # Verify no changes in DB
        self.customer_inside.refresh_from_db()
        self.assertIsNone(self.customer_inside.zone)

    def test_auto_assign_on_customer_save(self):
        """
        Verify that saving a Customer automatically triggers the pre-save signal
        to assign the correct zone.
        """
        # Reconnect pre-save signal for this test
        pre_save.connect(auto_assign_customer_zone, sender=Customer)

        connection.set_tenant(self.tenant)

        # Create a new customer inside the zone
        if HAS_GIS and Point:
            loc = Point(79.6, 21.6)
        else:
            loc = {"longitude": 79.6, "latitude": 21.6}

        new_customer = Customer.objects.create(
            name='Signal Inside Customer',
            email='signal_inside@example.com',
            location=loc,
            zone=None,
            is_active=True
        )

        # Verify the zone was auto-assigned at creation time
        self.assertEqual(new_customer.zone, self.zone)

    def test_auto_assign_on_zone_save(self):
        """
        Verify that saving/updating a Zone automatically triggers the post-save signal
        to assign that zone to matching customers.
        """
        # Reconnect post-save signal for this test
        post_save.connect(auto_assign_customers_on_zone_change, sender=Zone)

        connection.set_tenant(self.tenant)

        # We have self.customer_inside which has location (79.5, 21.5) and zone = None.
        # Let's create a NEW zone that also covers (79.5, 21.5).
        # Boundary: long 79.4 to 79.8, lat 21.4 to 21.8
        if HAS_GIS and Polygon:
            boundary2 = Polygon(((79.4, 21.4), (79.8, 21.4), (79.8, 21.8), (79.4, 21.8), (79.4, 21.4)))
        else:
            boundary2 = {
                "type": "Polygon",
                "coordinates": [
                    [[79.4, 21.4], [79.8, 21.4], [79.8, 21.8], [79.4, 21.8], [79.4, 21.4]]
                ]
            }

        new_zone = Zone.objects.create(
            name='Test Zone Sub-Central',
            description='Second zone',
            boundary=boundary2,
            is_active=True
        )

        # Refresh self.customer_inside from DB and verify it was automatically updated
        # to the new zone (since it lies inside it and the Zone was saved/created)
        self.customer_inside.refresh_from_db()
        self.assertEqual(self.customer_inside.zone, new_zone)

    def test_manual_zone_override_preserves(self):
        """
        Verify that manually assigning a zone (at creation or during update)
        is respected and not overwritten by coordinates calculation.
        """
        # Reconnect pre-save signal
        pre_save.connect(auto_assign_customer_zone, sender=Customer)
        connection.set_tenant(self.tenant)

        # 1. Test creation with explicit zone
        # Create a test customer with location inside self.zone, but manually assign a different zone
        other_zone = Zone.objects.create(
            name='Other Zone',
            description='Other zone description',
            boundary=self.zone.boundary,
            is_active=True
        )

        if HAS_GIS and Point:
            loc = Point(79.6, 21.6)
        else:
            loc = {"longitude": 79.6, "latitude": 21.6}

        customer_manual = Customer.objects.create(
            name='Customer Manual Creation',
            email='manual_create@example.com',
            location=loc,
            zone=other_zone,
            is_active=True
        )

        # The manually set other_zone should be preserved and NOT auto-assigned to self.zone
        self.assertEqual(customer_manual.zone, other_zone)

        # 2. Test manual zone override patch on existing customer
        # Update zone of customer_inside to other_zone
        self.customer_inside.zone = other_zone
        self.customer_inside.save()

        self.customer_inside.refresh_from_db()
        self.assertEqual(self.customer_inside.zone, other_zone)

        # 3. Test that updating other fields does not clear or override the manually set zone
        self.customer_inside.refresh_from_db()
        self.assertEqual(self.customer_inside.zone, other_zone)


class CustomerBulkQRTestCase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test City'
        tenant.state = 'Test State'
        tenant.code = 'TST'
        tenant.create_schema(sync_schema=True)

    def setUp(self):
        super().setUp()
        
        # Disconnect signals during setUp so they don't interfere
        pre_save.disconnect(auto_assign_customer_zone, sender=Customer)
        post_save.disconnect(auto_assign_customers_on_zone_change, sender=Zone)
        
        connection.set_tenant(self.tenant)
        User = get_user_model()

        # Create authorized CRM Manager user
        self.manager_user = User.objects.create_user(
            username='crm_manager_qr',
            email='manager_qr@example.com',
            password='testpassword',
            phone='9000000020',
            tenant_schema='test'
        )
        crm_group, _ = Group.objects.get_or_create(name='CRM_Managers')
        self.manager_user.groups.add(crm_group)

        # Restore tenant context
        connection.set_tenant(self.tenant)

        self.client = APIClient()
        self.client.force_authenticate(user=self.manager_user)

        # Create multiple active test customers
        self.cust1 = Customer.objects.create(
            name='Customer 1',
            email='c1@example.com',
            phone='1234567890',
            address='Address 1',
            is_active=True
        )
        self.cust2 = Customer.objects.create(
            name='Customer 2',
            email='c2@example.com',
            phone='1234567891',
            address='Address 2',
            is_active=True
        )
        self.cust3 = Customer.objects.create(
            name='Customer 3',
            email='c3@example.com',
            phone='1234567892',
            address='Address 3',
            is_active=True
        )
        # One inactive customer to ensure it is filtered out
        self.cust_inactive = Customer.objects.create(
            name='Inactive Customer',
            email='inactive@example.com',
            phone='1234567893',
            address='Address 4',
            is_active=False
        )

    def tearDown(self):
        # Reconnect signals
        pre_save.connect(auto_assign_customer_zone, sender=Customer)
        post_save.connect(auto_assign_customers_on_zone_change, sender=Zone)
        super().tearDown()

    def test_bulk_download_all_active(self):
        """
        Verify that bulk-download-qr without parameters downloads all active customers.
        """
        connection.set_tenant(self.tenant)
        url = '/api/erp/customers/bulk-download-qr/'
        response = self.client.get(url, HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        
        # Verify ZIP contains expected files
        import zipfile
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            namelist = zf.namelist()
            self.assertIn('qr_stickers.pdf', namelist)
            self.assertIn('qr_mapping.csv', namelist)
            
            # Read mapping CSV and check count (headers + 3 active customers = 4 lines)
            csv_content = zf.read('qr_mapping.csv').decode('utf-8')
            lines = [l for l in csv_content.splitlines() if l.strip()]
            self.assertEqual(len(lines), 4)

    def test_bulk_download_filter_get(self):
        """
        Verify that bulk-download-qr with GET query param filters by customer IDs.
        """
        connection.set_tenant(self.tenant)
        url = f'/api/erp/customers/bulk-download-qr/?ids={self.cust1.id},{self.cust2.id}'
        response = self.client.get(url, HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        
        import zipfile
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            csv_content = zf.read('qr_mapping.csv').decode('utf-8')
            lines = [l for l in csv_content.splitlines() if l.strip()]
            # headers + 2 selected customers = 3 lines
            self.assertEqual(len(lines), 3)
            self.assertIn(self.cust1.name, csv_content)
            self.assertIn(self.cust2.name, csv_content)
            self.assertNotIn(self.cust3.name, csv_content)

    def test_bulk_download_filter_post(self):
        """
        Verify that bulk-download-qr with POST request body filters by customer IDs.
        """
        connection.set_tenant(self.tenant)
        url = '/api/erp/customers/bulk-download-qr/'
        # Test with 'customer_ids' key in JSON payload
        response = self.client.post(
            url, 
            {'customer_ids': [self.cust2.id, self.cust3.id]}, 
            format='json', 
            HTTP_HOST='tenant.test.com'
        )
        self.assertEqual(response.status_code, 200)
        
        import zipfile
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            csv_content = zf.read('qr_mapping.csv').decode('utf-8')
            lines = [l for l in csv_content.splitlines() if l.strip()]
            # headers + 2 selected customers = 3 lines
            self.assertEqual(len(lines), 3)
            self.assertNotIn(self.cust1.name, csv_content)
            self.assertIn(self.cust2.name, csv_content)
            self.assertIn(self.cust3.name, csv_content)

    def test_bulk_download_invalid_ids_format(self):
        """
        Verify that invalid IDs or format returns a 400 Bad Request.
        """
        connection.set_tenant(self.tenant)
        url = '/api/erp/customers/bulk-download-qr/?ids=abc,def'
        response = self.client.get(url, HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 400)

    def test_bulk_download_no_matching_customers(self):
        """
        Verify that non-existent or inactive IDs returns a 404 Not Found.
        """
        import uuid
        connection.set_tenant(self.tenant)
        # Using a valid non-existent UUID and inactive customer ID to trigger 404
        non_existent_id = uuid.uuid4()
        url = f'/api/erp/customers/bulk-download-qr/?ids={non_existent_id},{self.cust_inactive.id}'
        response = self.client.get(url, HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 404)

    def test_single_download_qr_pdf(self):
        """
        Verify that download-qr endpoint returns a single-page PDF containing the QR label.
        """
        connection.set_tenant(self.tenant)
        url = f'/api/erp/customers/{self.cust1.id}/download-qr/'
        response = self.client.get(url, HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response['Content-Disposition'].startswith('attachment; filename="qr_sticker_customer_PENCH-'))
        self.assertTrue(response['Content-Disposition'].endswith('.pdf"'))

    def test_single_view_qr_png(self):
        """
        Verify that view-qr endpoint returns a PNG image of the QR label.
        """
        connection.set_tenant(self.tenant)
        url = f'/api/erp/customers/{self.cust1.id}/view-qr/'
        response = self.client.get(url, HTTP_HOST='tenant.test.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
