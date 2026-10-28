import datetime
import io
import json
import shutil
import tempfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django_tenants.test.cases import TenantTestCase
from PIL import Image
from rest_framework.test import APIClient

from crm.models import Customer
from finance.models import (
    MonthlyBill,
    BillStatus,
    OnlinePayment,
    OnlinePaymentPurpose,
    OnlinePaymentStatus,
)
from inventory.models import Product
from orders.models import Order, PaymentStatus

MEDIA_ROOT = tempfile.mkdtemp()
HOST = "tenant.test.com"


def make_screenshot(name="proof.png"):
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class TestOnlinePayments(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test City"
        tenant.state = "Test State"
        tenant.code = "TST"
        tenant.create_schema(sync_schema=True)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="admin_user",
            email="admin@example.com",
            password="testpassword",
            is_erp_user=True,
        )
        self.customer_user = User.objects.create_user(
            username="cust_user",
            email="cust@example.com",
            password="testpassword",
            is_customer=True,
        )
        if getattr(settings, "HAS_GDAL", False):
            from django.contrib.gis.geos import Point

            location = Point(73.85, 18.52)
        else:
            location = {"lat": 18.52, "lng": 73.85}
        self.customer = Customer.objects.create(
            name="Cust",
            email="cust@example.com",
            phone="9999999999",
            address="Pune",
            user=self.customer_user,
            location=location,
        )
        self.customer_user.tenant_schema = self.tenant.schema_name
        self.customer_user.save()

        self.product = Product.objects.create(name="Milk", sku="MILK1", unit_price=50)
        self.bill = MonthlyBill.objects.create(
            customer=self.customer,
            billing_month=datetime.date.today().replace(day=1),
            total_amount=1500,
            due_date=datetime.date.today(),
            invoice_number="INV-TEST-1",
        )

        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)
        self.customer_client = APIClient()
        self.customer_client.force_authenticate(user=self.customer_user)

    # ── Customer location ──────────────────────────────────────────

    def test_me_returns_customer_location(self):
        res = self.customer_client.get("/api/accounts/me/", HTTP_HOST=HOST)
        self.assertEqual(res.status_code, 200)
        loc = res.data["customer_location"]
        self.assertAlmostEqual(loc["latitude"], 18.52)
        self.assertAlmostEqual(loc["longitude"], 73.85)

    def test_me_returns_null_location_for_non_customer(self):
        res = self.admin_client.get("/api/accounts/me/", HTTP_HOST=HOST)
        self.assertIsNone(res.data["customer_location"])

    # ── Manual orders require a screenshot ─────────────────────────

    def _order_payload(self, **extra):
        payload = {
            "scheduled_delivery_date": str(datetime.date.today() + datetime.timedelta(days=1)),
            "items": json.dumps([{"product": str(self.product.id), "quantity": 2}]),
        }
        payload.update(extra)
        return payload

    def test_customer_manual_order_without_screenshot_is_rejected(self):
        res = self.customer_client.post(
            "/api/erp/orders/", self._order_payload(), format="multipart", HTTP_HOST=HOST
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("payment_screenshot", res.data)
        self.assertFalse(Order.objects.exists())

    def test_customer_manual_order_with_screenshot_creates_pending_payment(self):
        res = self.customer_client.post(
            "/api/erp/orders/",
            self._order_payload(payment_screenshot=make_screenshot()),
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(res.status_code, 201, res.data)
        order = Order.objects.get()
        self.assertTrue(order.is_special)
        payment = OnlinePayment.objects.get()
        self.assertEqual(payment.order, order)
        self.assertEqual(payment.purpose, OnlinePaymentPurpose.ORDER)
        self.assertEqual(payment.amount, order.total)
        self.assertEqual(payment.status, OnlinePaymentStatus.PENDING)
        self.assertEqual(res.data["latest_payment"]["status"], "pending")

        # Admin verifies -> order marked paid
        res = self.admin_client.post(
            f"/api/erp/finance/online-payments/{payment.id}/verify/", HTTP_HOST=HOST
        )
        self.assertEqual(res.status_code, 200, res.data)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, PaymentStatus.PAID)

    def test_admin_order_does_not_need_screenshot(self):
        payload = self._order_payload(customer=str(self.customer.id))
        res = self.admin_client.post(
            "/api/erp/orders/", payload, format="multipart", HTTP_HOST=HOST
        )
        self.assertEqual(res.status_code, 201, res.data)

    # ── Online payment submission & verification ───────────────────

    def test_customer_bill_payment_verify_records_transaction(self):
        res = self.customer_client.post(
            "/api/erp/finance/online-payments/",
            {
                "amount": "1500.00",
                "bill": str(self.bill.id),
                "transaction_id": "UTR123",
                "screenshot": make_screenshot(),
            },
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["purpose"], "bill")
        self.assertEqual(str(res.data["customer"]), str(self.customer.id))

        # Not counted against the bill until verified
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, BillStatus.UNPAID)

        # Customers cannot verify their own payments
        payment_id = res.data["id"]
        res = self.customer_client.post(
            f"/api/erp/finance/online-payments/{payment_id}/verify/", HTTP_HOST=HOST
        )
        self.assertEqual(res.status_code, 403)

        res = self.admin_client.post(
            f"/api/erp/finance/online-payments/{payment_id}/verify/", HTTP_HOST=HOST
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["status"], "verified")
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, BillStatus.PAID)
        self.assertEqual(self.bill.transactions.get().transaction_id, "UTR123")

        # Cannot verify twice
        res = self.admin_client.post(
            f"/api/erp/finance/online-payments/{payment_id}/verify/", HTTP_HOST=HOST
        )
        self.assertEqual(res.status_code, 400)

    def test_reject_requires_reason(self):
        payment = OnlinePayment.objects.create(
            customer=self.customer, amount=100, screenshot=make_screenshot()
        )
        url = f"/api/erp/finance/online-payments/{payment.id}/reject/"
        self.assertEqual(self.admin_client.post(url, HTTP_HOST=HOST).status_code, 400)
        res = self.admin_client.post(url, {"reason": "Blurry"}, HTTP_HOST=HOST)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "rejected")
        self.assertEqual(res.data["rejection_reason"], "Blurry")

    def test_summary_counts(self):
        OnlinePayment.objects.create(
            customer=self.customer, amount=100, screenshot=make_screenshot()
        )
        OnlinePayment.objects.create(
            customer=self.customer,
            amount=200,
            screenshot=make_screenshot(),
            status=OnlinePaymentStatus.VERIFIED,
        )
        res = self.admin_client.get(
            "/api/erp/finance/online-payments/summary/", HTTP_HOST=HOST
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["total_customers_paid_online"], 1)
        self.assertEqual(res.data["pending"]["count"], 1)
        self.assertEqual(res.data["verified"]["amount"], 200.0)

    def test_customer_sees_only_own_payments(self):
        other = Customer.objects.create(name="Other", phone="8888888888")
        OnlinePayment.objects.create(customer=other, amount=50, screenshot=make_screenshot())
        OnlinePayment.objects.create(
            customer=self.customer, amount=60, screenshot=make_screenshot()
        )
        res = self.customer_client.get("/api/erp/finance/online-payments/", HTTP_HOST=HOST)
        results = res.data["results"] if isinstance(res.data, dict) else res.data
        self.assertEqual(len(results), 1)
        self.assertEqual(float(results[0]["amount"]), 60.0)

    # ── Additional (non-subscription) orders summary ───────────────

    def test_special_orders_summary(self):
        self.customer_client.post(
            "/api/erp/orders/",
            self._order_payload(payment_screenshot=make_screenshot()),
            format="multipart",
            HTTP_HOST=HOST,
        )
        res = self.admin_client.get("/api/erp/orders/special-summary/", HTTP_HOST=HOST)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["new_pending"], 1)
        self.assertEqual(res.data["placed_last_24h"], 1)
        self.assertEqual(res.data["upcoming"], 1)
        self.assertEqual(res.data["payment_pending_verification"], 1)
        self.assertEqual(len(res.data["recent_new_orders"]), 1)

        # Customers cannot see the admin summary
        res = self.customer_client.get("/api/erp/orders/special-summary/", HTTP_HOST=HOST)
        self.assertEqual(res.status_code, 403)

    # ── Customer subscribing with an online payment ────────────────

    def test_customer_subscription_with_payment_is_scoped_to_self(self):
        other = Customer.objects.create(name="Other", phone="7777777777")
        res = self.customer_client.post(
            "/api/erp/subscriptions/",
            {
                "customer": str(other.id),  # must be ignored for customers
                "frequency": "custom",
                "custom_days": "[0, 2, 4]",
                "start_date": str(datetime.date.today() + datetime.timedelta(days=1)),
                "items": json.dumps([{"product": str(self.product.id), "quantity": 1}]),
                "payment_amount": "650.00",
                "payment_screenshot": make_screenshot(),
            },
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(str(res.data["customer"]), str(self.customer.id))
        self.assertEqual(res.data["custom_days"], [0, 2, 4])
        payment = OnlinePayment.objects.get()
        self.assertEqual(payment.purpose, OnlinePaymentPurpose.SUBSCRIPTION)
        self.assertEqual(payment.customer, self.customer)
        self.assertEqual(res.data["latest_payment"]["status"], "pending")

    def test_grouped_summary_includes_product_id(self):
        from subscriptions.models import Subscription, SubscriptionItem

        sub = Subscription.objects.create(
            customer=self.customer, start_date=datetime.date.today()
        )
        SubscriptionItem.objects.create(subscription=sub, product=self.product, quantity=1)
        res = self.customer_client.get(
            "/api/erp/subscriptions/grouped-summary/", HTTP_HOST=HOST
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data[0]["product_id"], str(self.product.id))
        self.assertEqual(res.data[0]["unit_price"], 50.0)

    def test_order_price_always_comes_from_inventory(self):
        res = self.customer_client.post(
            "/api/erp/orders/",
            self._order_payload(
                items=json.dumps([
                    {"product": str(self.product.id), "quantity": 2, "unit_price": "1.00"}
                ]),
                payment_screenshot=make_screenshot(),
            ),
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(res.status_code, 201, res.data)
        order = Order.objects.get()
        # Product.unit_price is 50 -> 2 x 50, the client-sent 1.00 is ignored
        self.assertEqual(order.total, 100)
        self.assertEqual(OnlinePayment.objects.get().amount, 100)

    # ── Fractional quantities ──────────────────────────────────────

    def test_fractional_subscription_quantity(self):
        res = self.customer_client.post(
            "/api/erp/subscriptions/",
            {
                "frequency": "daily",
                "start_date": str(datetime.date.today() + datetime.timedelta(days=1)),
                "items": json.dumps([{"product": str(self.product.id), "quantity": 1.5}]),
            },
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(res.status_code, 201, res.data)
        # Returned as a JSON number, not a string
        self.assertEqual(res.data["items"][0]["quantity"], 1.5)

    def test_fractional_order_total_and_bottles(self):
        from decimal import Decimal
        from inventory.models import BottleType

        bottle = BottleType.objects.create(name="1L Glass", volume_ml=1000)
        self.product.bottle_type = bottle
        self.product.is_returnable = True
        self.product.save()

        res = self.customer_client.post(
            "/api/erp/orders/",
            self._order_payload(
                items=json.dumps([{"product": str(self.product.id), "quantity": 1.5}]),
                payment_screenshot=make_screenshot(),
            ),
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(res.status_code, 201, res.data)
        order = Order.objects.get()
        item = order.items.get()
        self.assertEqual(item.quantity, Decimal("1.50"))
        self.assertEqual(order.total, Decimal("75.00"))  # 1.5 x 50
        self.assertEqual(item.bottle_count, 2)  # a part-filled bottle still needs a bottle

    def test_zero_quantity_rejected(self):
        res = self.customer_client.post(
            "/api/erp/subscriptions/",
            {
                "frequency": "daily",
                "start_date": str(datetime.date.today()),
                "items": json.dumps([{"product": str(self.product.id), "quantity": 0}]),
            },
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(res.status_code, 400)

    # ── Subscription visibility ────────────────────────────────────

    def test_customer_only_sees_own_subscriptions(self):
        from subscriptions.models import Subscription

        other = Customer.objects.create(name="Other", phone="6666666666")
        mine = Subscription.objects.create(customer=self.customer, start_date=datetime.date.today())
        theirs = Subscription.objects.create(customer=other, start_date=datetime.date.today())

        res = self.customer_client.get("/api/erp/subscriptions/", HTTP_HOST=HOST)
        results = res.data["results"] if isinstance(res.data, dict) else res.data
        self.assertEqual([r["id"] for r in results], [str(mine.id)])

        # Cannot open or pause someone else's subscription
        res = self.customer_client.get(f"/api/erp/subscriptions/{theirs.id}/", HTTP_HOST=HOST)
        self.assertEqual(res.status_code, 404)
        res = self.customer_client.post(
            f"/api/erp/subscriptions/{theirs.id}/pause/",
            {"pause_start": str(datetime.date.today()), "pause_end": str(datetime.date.today())},
            HTTP_HOST=HOST,
        )
        self.assertEqual(res.status_code, 404)

        # Admins still see everything
        res = self.admin_client.get("/api/erp/subscriptions/", HTTP_HOST=HOST)
        results = res.data["results"] if isinstance(res.data, dict) else res.data
        self.assertEqual(len(results), 2)
