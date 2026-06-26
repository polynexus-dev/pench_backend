from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from crm.models import Customer
from subscriptions.models import Subscription, DeliveryFrequency, SubscriptionStatus
from inventory.models import Product
import datetime


class TestSubscriptionVacationTracking(TenantTestCase):
    """Unit tests for pause_updated_by vacation tracking field."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test City"
        tenant.state = "Test State"
        tenant.code = "TST"
        tenant.create_schema(sync_schema=True)

    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.user = User.objects.create_user(
            username="test_user",
            email="test@example.com",
            password="testpassword",
            is_erp_user=True,
            tenant_schema="test",
        )

        self.customer = Customer.objects.create(
            name="Test Customer", email="customer@example.com"
        )
        self.product = Product.objects.create(
            name="Test Milk", sku="TMILK1", unit_price=50.00
        )
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            status=SubscriptionStatus.ACTIVE,
            frequency=DeliveryFrequency.DAILY,
            start_date=datetime.date.today(),
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_pause_sets_pause_updated_by(self):
        url = f"/api/erp/subscriptions/{self.subscription.pk}/pause/"
        data = {
            "pause_start": str(datetime.date.today()),
            "pause_end": str(datetime.date.today() + datetime.timedelta(days=5)),
        }

        response = self.client.post(url, data, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.pause_updated_by, self.user)
        self.assertEqual(response.data["pause_updated_by"], self.user.pk)
        self.assertEqual(
            response.data["pause_updated_by_name"],
            self.user.get_full_name() or self.user.username,
        )

    def test_resume_sets_pause_updated_by(self):
        # Set initial pause
        self.subscription.is_paused = True
        self.subscription.pause_start = datetime.date.today()
        self.subscription.pause_end = datetime.date.today() + datetime.timedelta(days=5)
        self.subscription.save()

        url = f"/api/erp/subscriptions/{self.subscription.pk}/resume/"

        response = self.client.post(url, {}, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.pause_updated_by, self.user)
        self.assertFalse(self.subscription.is_paused)

    def test_get_grouped_summary(self):
        from subscriptions.models import SubscriptionItem
        SubscriptionItem.objects.create(
            subscription=self.subscription,
            product=self.product,
            quantity=2
        )

        url = "/api/erp/subscriptions/grouped-summary/"
        response = self.client.get(url, HTTP_HOST="tenant.test.com")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 1)
        
        item = response.data[0]
        self.assertEqual(item["frequency"], "daily")
        self.assertEqual(item["product_name"], self.product.name)
        self.assertEqual(item["quantity"], 2)
        self.assertEqual(item["count"], 1)
        self.assertEqual(item["label"], f"Daily - 2x {self.product.name}")


