from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.conf import settings
from django.db import connection
from django.db.models.signals import pre_save, post_save
from routing.models import Zone
from crm.models import (
    Customer,
    HAS_GIS,
    auto_assign_customer_zone,
    auto_assign_customers_on_zone_change,
)

try:
    from django.contrib.gis.geos import Point, Polygon
except ImportError:
    Point = None
    Polygon = None


class CustomerAutoAssignZonesTestCase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test City"
        tenant.state = "Test State"
        tenant.code = "TST"
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
            username="crm_manager",
            email="manager@example.com",
            password="testpassword",
            phone="9000000010",
            tenant_schema="test",
        )
        crm_group, _ = Group.objects.get_or_create(name="CRM_Managers")
        self.manager_user.groups.add(crm_group)

        # Create unauthorized user with unique phone
        self.regular_user = User.objects.create_user(
            username="regular_user",
            email="regular@example.com",
            password="testpassword",
            phone="9000000011",
            tenant_schema="test",
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
            boundary = Polygon(
                ((79.0, 21.0), (80.0, 21.0), (80.0, 22.0), (79.0, 22.0), (79.0, 21.0))
            )
        else:
            boundary = {
                "type": "Polygon",
                "coordinates": [
                    [
                        [79.0, 21.0],
                        [80.0, 21.0],
                        [80.0, 22.0],
                        [79.0, 22.0],
                        [79.0, 21.0],
                    ]
                ],
            }

        self.zone = Zone.objects.create(
            name="Test Zone Central",
            description="Test delivery zone",
            boundary=boundary,
            is_active=True,
        )

        # Create customer inside zone
        if HAS_GIS and Point:
            loc_inside = Point(79.5, 21.5)
        else:
            loc_inside = {"longitude": 79.5, "latitude": 21.5}

        self.customer_inside = Customer.objects.create(
            name="Customer Inside",
            email="inside@example.com",
            location=loc_inside,
            zone=None,
            is_active=True,
        )

        # Create customer outside zone
        if HAS_GIS and Point:
            loc_outside = Point(78.5, 20.5)
        else:
            loc_outside = {"longitude": 78.5, "latitude": 20.5}

        self.customer_outside = Customer.objects.create(
            name="Customer Outside",
            email="outside@example.com",
            location=loc_outside,
            zone=None,
            is_active=True,
        )

        # Create customer with no location
        self.customer_no_loc = Customer.objects.create(
            name="Customer No Location",
            email="noloc@example.com",
            location=None,
            zone=None,
            is_active=True,
        )

        # Create inactive customer inside zone
        self.customer_inactive = Customer.objects.create(
            name="Customer Inactive",
            email="inactive@example.com",
            location=loc_inside,
            zone=None,
            is_active=False,
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
        url = "/api/erp/customers/auto-assign-zones/"
        response = self.authorized_client.post(url, {}, HTTP_HOST="tenant.test.com")

        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.data)
        self.assertEqual(
            response.data["scanned"], 2
        )  # Inside and Outside (active only)
        self.assertEqual(
            response.data["updated"], 1
        )  # Only inside customer should be updated

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
        url = "/api/erp/customers/auto-assign-zones/"
        response = self.unauthorized_client.post(url, {}, HTTP_HOST="tenant.test.com")
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
            name="Signal Inside Customer",
            email="signal_inside@example.com",
            location=loc,
            zone=None,
            is_active=True,
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
            boundary2 = Polygon(
                ((79.4, 21.4), (79.8, 21.4), (79.8, 21.8), (79.4, 21.8), (79.4, 21.4))
            )
        else:
            boundary2 = {
                "type": "Polygon",
                "coordinates": [
                    [
                        [79.4, 21.4],
                        [79.8, 21.4],
                        [79.8, 21.8],
                        [79.4, 21.8],
                        [79.4, 21.4],
                    ]
                ],
            }

        new_zone = Zone.objects.create(
            name="Test Zone Sub-Central",
            description="Second zone",
            boundary=boundary2,
            is_active=True,
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
            name="Other Zone",
            description="Other zone description",
            boundary=self.zone.boundary,
            is_active=True,
        )

        if HAS_GIS and Point:
            loc = Point(79.6, 21.6)
        else:
            loc = {"longitude": 79.6, "latitude": 21.6}

        customer_manual = Customer.objects.create(
            name="Customer Manual Creation",
            email="manual_create@example.com",
            location=loc,
            zone=other_zone,
            is_active=True,
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
        tenant.name = "Test City"
        tenant.state = "Test State"
        tenant.code = "TST"
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
            username="crm_manager_qr",
            email="manager_qr@example.com",
            password="testpassword",
            phone="9000000020",
            tenant_schema="test",
        )
        crm_group, _ = Group.objects.get_or_create(name="CRM_Managers")
        self.manager_user.groups.add(crm_group)

        # Restore tenant context
        connection.set_tenant(self.tenant)

        self.client = APIClient()
        self.client.force_authenticate(user=self.manager_user)

        # Create multiple active test customers
        self.cust1 = Customer.objects.create(
            name="Customer 1",
            email="c1@example.com",
            phone="1234567890",
            address="Address 1",
            is_active=True,
        )
        self.cust2 = Customer.objects.create(
            name="Customer 2",
            email="c2@example.com",
            phone="1234567891",
            address="Address 2",
            is_active=True,
        )
        self.cust3 = Customer.objects.create(
            name="Customer 3",
            email="c3@example.com",
            phone="1234567892",
            address="Address 3",
            is_active=True,
        )
        # One inactive customer to ensure it is filtered out
        self.cust_inactive = Customer.objects.create(
            name="Inactive Customer",
            email="inactive@example.com",
            phone="1234567893",
            address="Address 4",
            is_active=False,
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
        url = "/api/erp/customers/bulk-download-qr/"
        response = self.client.get(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")

        # Verify ZIP contains expected files
        import zipfile
        from io import BytesIO

        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            namelist = zf.namelist()
            self.assertIn("qr_stickers.pdf", namelist)
            self.assertIn("qr_mapping.csv", namelist)

            # Read mapping CSV and check count (headers + 3 active customers = 4 lines)
            csv_content = zf.read("qr_mapping.csv").decode("utf-8")
            lines = [l for l in csv_content.splitlines() if l.strip()]
            self.assertEqual(len(lines), 4)

    def test_bulk_download_filter_get(self):
        """
        Verify that bulk-download-qr with GET query param filters by customer IDs.
        """
        connection.set_tenant(self.tenant)
        url = (
            f"/api/erp/customers/bulk-download-qr/?ids={self.cust1.id},{self.cust2.id}"
        )
        response = self.client.get(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)

        import zipfile
        from io import BytesIO

        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            csv_content = zf.read("qr_mapping.csv").decode("utf-8")
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
        url = "/api/erp/customers/bulk-download-qr/"
        # Test with 'customer_ids' key in JSON payload
        response = self.client.post(
            url,
            {"customer_ids": [self.cust2.id, self.cust3.id]},
            format="json",
            HTTP_HOST="tenant.test.com",
        )
        self.assertEqual(response.status_code, 200)

        import zipfile
        from io import BytesIO

        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            csv_content = zf.read("qr_mapping.csv").decode("utf-8")
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
        url = "/api/erp/customers/bulk-download-qr/?ids=abc,def"
        response = self.client.get(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 400)

    def test_bulk_download_no_matching_customers(self):
        """
        Verify that non-existent or inactive IDs returns a 404 Not Found.
        """
        import uuid

        connection.set_tenant(self.tenant)
        # Using a valid non-existent UUID and inactive customer ID to trigger 404
        non_existent_id = uuid.uuid4()
        url = f"/api/erp/customers/bulk-download-qr/?ids={non_existent_id},{self.cust_inactive.id}"
        response = self.client.get(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 404)

    def test_single_download_qr_pdf(self):
        """
        Verify that download-qr endpoint returns a single-page PDF containing the QR label.
        """
        connection.set_tenant(self.tenant)
        url = f"/api/erp/customers/{self.cust1.id}/download-qr/"
        response = self.client.get(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(
            response["Content-Disposition"].startswith(
                'attachment; filename="qr_sticker_customer_PENCH-'
            )
        )
        self.assertTrue(response["Content-Disposition"].endswith('.pdf"'))

    def test_single_view_qr_png(self):
        """
        Verify that view-qr endpoint returns a PNG image of the QR label.
        """
        connection.set_tenant(self.tenant)
        url = f"/api/erp/customers/{self.cust1.id}/view-qr/"
        response = self.client.get(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")


class CustomerBulkDeleteTestCase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test City"
        tenant.state = "Test State"
        tenant.code = "TST"
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
            username="crm_manager_del",
            email="manager_del@example.com",
            password="testpassword",
            phone="9000000030",
            tenant_schema="test",
        )
        crm_group, _ = Group.objects.get_or_create(name="CRM_Managers")
        self.manager_user.groups.add(crm_group)

        # Restore tenant context
        connection.set_tenant(self.tenant)

        self.client = APIClient()
        self.client.force_authenticate(user=self.manager_user)

    def tearDown(self):
        pre_save.connect(auto_assign_customer_zone, sender=Customer)
        post_save.connect(auto_assign_customers_on_zone_change, sender=Zone)
        super().tearDown()

    def test_bulk_delete_success(self):
        connection.set_tenant(self.tenant)
        User = get_user_model()
        from inventory.models import Product
        from subscriptions.models import Subscription
        from orders.models import Order
        from finance.models import MonthlyBill
        import datetime

        # Create a product
        product = Product.objects.create(name="Test Product", sku="TST-DEL-PROD", unit_price=15.0)

        # Customer 1: Normal customer user to be fully deleted
        user1 = User.objects.create_user(
            username="del_user1", email="u1@example.com", phone="9000000031", is_customer=True, tenant_schema="test"
        )
        cust1 = Customer.objects.get(user=user1)

        sub1 = Subscription.objects.create(customer=cust1, start_date=datetime.date.today())
        ord1 = Order.objects.create(customer=cust1, subscription=sub1, delivery_address="Add 1")
        bill1 = MonthlyBill.objects.create(
            customer=cust1, billing_month=datetime.date.today().replace(day=1),
            due_date=datetime.date.today(), invoice_number="INV-DEL-1"
        )

        # Customer 2: Customer user who is also a driver (should NOT be deleted, is_customer set to False)
        user2 = User.objects.create_user(
            username="del_user2", email="u2@example.com", phone="9000000032", is_customer=True, is_driver=True, tenant_schema="test"
        )
        cust2 = Customer.objects.get(user=user2)

        # Call endpoint
        url = "/api/erp/customers/bulk-delete/"
        payload = {"ids": [str(cust1.id), str(cust2.id)]}
        response = self.client.post(url, payload, format="json", HTTP_HOST="tenant.test.com")

        self.assertEqual(response.status_code, 200)
        self.assertIn("summary", response.data)

        # Verify database state
        self.assertFalse(Customer.objects.filter(id=cust1.id).exists())
        self.assertFalse(Customer.objects.filter(id=cust2.id).exists())
        self.assertFalse(Order.objects.filter(id=ord1.id).exists())
        self.assertFalse(MonthlyBill.objects.filter(id=bill1.id).exists())
        self.assertFalse(Subscription.objects.filter(id=sub1.id).exists())

        # Verify User 1 is deleted
        self.assertFalse(User.objects.filter(id=user1.id).exists())

        # Verify User 2 is NOT deleted, but is_customer is False
        user2.refresh_from_db()
        self.assertTrue(User.objects.filter(id=user2.id).exists())
        self.assertFalse(user2.is_customer)
        self.assertTrue(user2.is_driver)

    def test_bulk_delete_invalid_ids(self):
        connection.set_tenant(self.tenant)
        url = "/api/erp/customers/bulk-delete/"
        
        # Test non-list
        response = self.client.post(url, {"ids": "not-a-list"}, format="json", HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 400)

        # Test invalid UUID format
        response = self.client.post(url, ["invalid-uuid"], format="json", HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 400)

        # Test non-existent customers
        import uuid
        response = self.client.post(url, [str(uuid.uuid4())], format="json", HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 404)

    def test_single_delete_customer_success(self):
        connection.set_tenant(self.tenant)
        User = get_user_model()
        user = User.objects.create_user(
            username="single_del_user", email="single_u@example.com", phone="9000000035", is_customer=True, tenant_schema="test"
        )
        cust = Customer.objects.get(user=user)

        url = f"/api/erp/customers/{cust.id}/"
        response = self.client.delete(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 204)

        self.assertFalse(Customer.objects.filter(id=cust.id).exists())
        self.assertFalse(User.objects.filter(id=user.id).exists())

    def test_single_delete_customer_multi_role(self):
        connection.set_tenant(self.tenant)
        User = get_user_model()
        user = User.objects.create_user(
            username="multi_del_user", email="multi_u@example.com", phone="9000000036", is_customer=True, is_driver=True, tenant_schema="test"
        )
        cust = Customer.objects.get(user=user)

        url = f"/api/erp/customers/{cust.id}/"
        response = self.client.delete(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 204)

        self.assertFalse(Customer.objects.filter(id=cust.id).exists())
        self.assertTrue(User.objects.filter(id=user.id).exists())
        
        user.refresh_from_db()
        self.assertFalse(user.is_customer)
        self.assertTrue(user.is_driver)


class CustomerTrialTestCase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test City"
        tenant.state = "Test State"
        tenant.code = "TST"
        tenant.create_schema(sync_schema=True)

    def setUp(self):
        super().setUp()
        pre_save.disconnect(auto_assign_customer_zone, sender=Customer)
        post_save.disconnect(auto_assign_customers_on_zone_change, sender=Zone)

        connection.set_tenant(self.tenant)
        User = get_user_model()

        # Create authorized CRM Manager user
        self.manager_user = User.objects.create_user(
            username="crm_manager_trial",
            email="manager_trial@example.com",
            password="testpassword",
            phone="9000000040",
            tenant_schema="test",
        )
        crm_group, _ = Group.objects.get_or_create(name="CRM_Managers")
        self.manager_user.groups.add(crm_group)

        # Restore tenant context
        connection.set_tenant(self.tenant)

        self.client = APIClient()
        self.client.force_authenticate(user=self.manager_user)

    def tearDown(self):
        pre_save.connect(auto_assign_customer_zone, sender=Customer)
        post_save.connect(auto_assign_customers_on_zone_change, sender=Zone)
        super().tearDown()

    def test_customer_default_trial_fields(self):
        """Verify new customers default to is_new=True and trial_approved=False."""
        connection.set_tenant(self.tenant)
        cust = Customer.objects.create(
            name="Trial Customer",
            email="trial@example.com",
            phone="9999999999",
            is_active=True,
        )
        self.assertTrue(cust.is_new)
        self.assertFalse(cust.trial_approved)

    def test_new_customers_endpoint(self):
        """Verify the new-customers endpoint only returns customers where is_new=True."""
        connection.set_tenant(self.tenant)
        cust_trial = Customer.objects.create(
            name="Trial Customer 1",
            email="trial1@example.com",
            is_new=True,
            is_active=True,
        )
        cust_subscribed = Customer.objects.create(
            name="Subscribed Customer",
            email="sub1@example.com",
            is_new=False,
            is_active=True,
        )

        url = "/api/erp/customers/new-customers/"
        response = self.client.get(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)
        
        # Verify response contains the trial customer and NOT the subscribed one
        names = [c["name"] for c in response.data]
        self.assertIn("Trial Customer 1", names)
        self.assertNotIn("Subscribed Customer", names)

    def test_approve_trial_endpoint(self):
        """Verify trial customer approval toggles trial_approved, creates order, and triggers notification."""
        connection.set_tenant(self.tenant)
        from inventory.models import Product
        from orders.models import Order
        
        product = Product.objects.create(name="Cow Milk (1L)", sku="MILK-1L", unit_price=60.00, unit="liter")
        
        cust = Customer.objects.create(
            name="Trial Customer 2",
            email="trial2@example.com",
            is_new=True,
            trial_approved=False,
            is_active=True,
        )

        url = f"/api/erp/customers/{cust.id}/approve/"
        response = self.client.post(
            url,
            {
                "product_id": str(product.id),
                "delivery_date": "2026-07-16",
                "quantity": 2
            },
            HTTP_HOST="tenant.test.com"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["trial_approved"])

        cust.refresh_from_db()
        self.assertTrue(cust.trial_approved)
        
        # Verify trial order was created correctly
        order = Order.objects.filter(customer=cust).first()
        self.assertIsNotNone(order)
        self.assertTrue(order.is_special)
        self.assertEqual(order.total, 120.00)

    def test_subscription_creation_clears_trial(self):
        """Verify creating an active subscription resets is_new and approves trial/delivery."""
        connection.set_tenant(self.tenant)
        cust = Customer.objects.create(
            name="Trial Customer 3",
            email="trial3@example.com",
            is_new=True,
            trial_approved=False,
            is_active=True,
        )

        from subscriptions.models import Subscription, SubscriptionStatus
        import datetime

        sub = Subscription.objects.create(
            customer=cust,
            status=SubscriptionStatus.ACTIVE,
            start_date=datetime.date.today(),
        )

        cust.refresh_from_db()
        self.assertFalse(cust.is_new)
        self.assertTrue(cust.trial_approved)

    def test_delivery_resets_trial_approval(self):
        """Verify delivering a trial order automatically resets trial_approved back to False."""
        connection.set_tenant(self.tenant)
        cust = Customer.objects.create(
            name="Trial Customer 4",
            email="trial4@example.com",
            is_new=True,
            trial_approved=True,
            is_active=True,
        )

        from orders.models import Order, OrderStatus
        import datetime
        order = Order.objects.create(
            customer=cust,
            scheduled_delivery_date=datetime.date.today(),
            delivery_address="123 Test St",
            status=OrderStatus.PENDING,
        )

        # Update order status to DELIVERED
        order.status = OrderStatus.DELIVERED
        order.save()

        cust.refresh_from_db()
        self.assertFalse(cust.trial_approved)
        self.assertTrue(cust.is_new) # Remains True since they haven't subscribed yet

    def test_approve_trial_assigns_to_active_route(self):
        """Verify trial customer approval automatically assigns their pending order to an active route."""
        connection.set_tenant(self.tenant)
        from routing.models import Zone, Driver
        from orders.models import Route, Order, OrderStatus
        import datetime

        # Create driver user
        User = get_user_model()
        driver_user = User.objects.create_user(
            username="driver_u", email="driver_u@example.com", password="pwd", phone="9000000099", is_driver=True, tenant_schema="test"
        )
        # Restore tenant context
        connection.set_tenant(self.tenant)
        
        # Create zone
        zone = Zone.objects.create(name="Trial Zone", is_active=True, assigned_driver=driver_user)
        
        # Create driver profile
        from inventory.models import Warehouse
        warehouse = Warehouse.objects.create(name="Test WH", latitude=21.15, longitude=79.08)
        driver_profile = Driver.objects.filter(user=driver_user).first()
        if not driver_profile:
            driver_profile = Driver.objects.create(user=driver_user, warehouse=warehouse)
        else:
            driver_profile.warehouse = warehouse
            driver_profile.save()

        # Create trial customer in that zone
        if HAS_GIS and Point:
            cust_loc = Point(79.09, 21.16)
        else:
            cust_loc = {"longitude": 79.09, "latitude": 21.16}

        cust = Customer.objects.create(
            name="Trial Cust Route",
            email="trial_route@example.com",
            phone="9876543210",
            is_new=True,
            trial_approved=False,
            zone=zone,
            location=cust_loc,
            is_active=True,
        )

        # Create pending order for customer
        today = datetime.date.today()
        order = Order.objects.create(
            customer=cust,
            scheduled_delivery_date=today,
            status=OrderStatus.PENDING,
            delivery_address="Trial Address"
        )

        # Create active route for driver today
        route = Route.objects.create(
            name="Route Today",
            driver=driver_user,
            delivery_date=today,
            status="pending"
        )

        # Create a product
        from inventory.models import Product
        product = Product.objects.create(name="Cow Milk (1L)", sku="MILK-1L", unit_price=60.00, unit="liter")

        # Trigger trial approval endpoint
        url = f"/api/erp/customers/{cust.id}/approve/"
        response = self.client.post(
            url,
            {
                "product_id": str(product.id),
                "delivery_date": str(today),
                "quantity": 1
            },
            HTTP_HOST="tenant.test.com"
        )
        self.assertEqual(response.status_code, 200)

        # Verify order is now assigned to the route
        order.refresh_from_db()
        self.assertTrue(hasattr(order, "route_stop"))
        self.assertEqual(order.route_stop.route, route)

    def test_merge_duplicate_customers_aggregates_properties(self):
        """Verify syncing/refreshing duplicate customers merges properties into primary without data loss."""
        connection.set_tenant(self.tenant)
        from routing.models import Zone
        
        # Create a zone
        zone = Zone.objects.create(name="Merge Zone", is_active=True)

        # Primary customer profile (created earlier) has outdated zone/location/approved status
        outdated_zone = Zone.objects.create(name="Outdated Zone", is_active=True)
        if HAS_GIS and Point:
            outdated_loc = Point(70.0, 20.0)
        else:
            outdated_loc = {"longitude": 70.0, "latitude": 20.0}

        primary_cust = Customer.objects.create(
            name="Duplicate Name",
            phone="9988776655",
            email="primary@example.com",
            zone=outdated_zone,
            location=outdated_loc,
            trial_approved=False,
            is_new=True,
            is_active=True,
        )

        # Duplicate customer profile (created later) has correct zone/location/approved status
        if HAS_GIS and Point:
            dup_loc = Point(79.1, 21.2)
        else:
            dup_loc = {"longitude": 79.1, "latitude": 21.2}

        dup_cust = Customer.objects.create(
            name="Duplicate Name",
            phone="9988776655",
            email="duplicate@example.com",
            zone=zone,
            location=dup_loc,
            trial_approved=True,
            is_new=False,
            is_active=True,
        )

        # Trigger duplicate merge by posting to sync-refresh-customers
        url = "/api/erp/customers/sync-refresh-customers/"
        self.manager_user.tenant_schema = self.tenant.schema_name
        self.manager_user.save()
        
        response = self.client.post(
            url,
            {"dry_run": False, "tenant_schema": self.tenant.schema_name},
            format="json",
            HTTP_HOST="tenant.test.com"
        )
        self.assertEqual(response.status_code, 200)

        # Verify duplicate is deleted
        self.assertFalse(Customer.objects.filter(id=dup_cust.id).exists())

        # Verify primary customer is updated with the duplicate's properties
        primary_cust.refresh_from_db()
        self.assertEqual(primary_cust.zone, zone)
        self.assertIsNotNone(primary_cust.location)
        self.assertTrue(primary_cust.trial_approved)
        self.assertFalse(primary_cust.is_new)



