from django.db import models
from django.db.models import Sum
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from core.models import BaseModel


class BillStatus(models.TextChoices):
    UNPAID = "unpaid", "Unpaid"
    PARTIAL = "partial", "Partially Paid"
    PAID = "paid", "Paid"
    CANCELLED = "cancelled", "Cancelled"


class MonthlyBill(BaseModel):
    """
    Summarizes all deliveries for a customer in a specific month.
    """

    customer = models.ForeignKey(
        "crm.Customer", on_delete=models.PROTECT, related_name="monthly_bills"
    )
    billing_month = models.DateField(
        help_text="The first day of the month being billed."
    )
    handling_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Packing and handling charges applied to the monthly bill based on slab.",
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, choices=BillStatus.choices, default=BillStatus.UNPAID
    )
    due_date = models.DateField()
    invoice_number = models.CharField(max_length=50, unique=True)

    # Optional: PDF Invoice link
    invoice_pdf = models.FileField(upload_to="invoices/", null=True, blank=True)

    class Meta:
        ordering = ["-billing_month"]
        unique_together = ("customer", "billing_month")

    def __str__(self):
        return f"Bill {self.invoice_number} - {self.customer.name} ({self.billing_month.strftime('%b %Y')})"

    @property
    def remaining_amount(self):
        return self.total_amount - self.amount_paid

    def reconcile(self):
        """
        Recalculates amount_paid from all linked transactions and updates status automatically.
        Called after any Transaction is created or deleted.
        """
        total_paid = self.transactions.aggregate(total=Sum("amount"))["total"] or 0
        self.amount_paid = total_paid

        if total_paid <= 0:
            self.status = BillStatus.UNPAID
        elif total_paid >= self.total_amount:
            self.status = BillStatus.PAID
        else:
            self.status = BillStatus.PARTIAL

        self.save(update_fields=["amount_paid", "status"])


class Transaction(BaseModel):
    """
    Records payments made against bills.
    """

    bill = models.ForeignKey(
        MonthlyBill, on_delete=models.CASCADE, related_name="transactions"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50, default="online")
    transaction_id = models.CharField(max_length=100, blank=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Payment of {self.amount} for {self.bill.invoice_number}"


class OnlinePaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending Verification"
    VERIFIED = "verified", "Verified"
    REJECTED = "rejected", "Rejected"


class OnlinePaymentPurpose(models.TextChoices):
    SUBSCRIPTION = "subscription", "Subscription"
    ORDER = "order", "Additional Order"
    BILL = "bill", "Monthly Bill"
    GENERAL = "general", "General"


class OnlinePayment(BaseModel):
    """
    A payment made online by a customer (either manual UPI screenshot or PayU gateway).
    Manual screenshot payments stay PENDING until an admin verifies or rejects them;
    PayU gateway payments are automatically verified/rejected via signed PayU callback/webhook.
    Verifying a payment linked to a bill records a Transaction against that bill.
    """

    customer = models.ForeignKey(
        "crm.Customer", on_delete=models.PROTECT, related_name="online_payments"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    screenshot = models.ImageField(
        upload_to="online_payments/", null=True, blank=True
    )
    transaction_id = models.CharField(
        max_length=100, blank=True, help_text="UPI Transaction Ref / UTR / Bank Ref"
    )
    payment_gateway = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Gateway identifier (e.g. 'payu') or blank for manual screenshot upload.",
    )
    gateway_txnid = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Merchant transaction ID (txnid) sent to the payment gateway.",
    )
    gateway_mihpayid = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="PayU payment ID (mihpayid) returned by the gateway.",
    )
    gateway_mode = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Payment mode used on gateway (e.g. UPI, CC, DC, NB).",
    )
    gateway_raw_response = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw callback/webhook payload received from the payment gateway.",
    )
    purpose = models.CharField(
        max_length=20,
        choices=OnlinePaymentPurpose.choices,
        default=OnlinePaymentPurpose.GENERAL,
    )
    subscription = models.ForeignKey(
        "subscriptions.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="online_payments",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="online_payments",
    )
    bill = models.ForeignKey(
        MonthlyBill,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="online_payments",
    )
    notes = models.TextField(blank=True, default="")

    status = models.CharField(
        max_length=20,
        choices=OnlinePaymentStatus.choices,
        default=OnlinePaymentStatus.PENDING,
    )
    submitted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_online_payments",
    )
    verified_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_online_payments",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")
    bill_transaction = models.OneToOneField(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="online_payment",
        help_text="Bill transaction recorded when this payment was verified.",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Online payment {self.amount} by {self.customer.name} ({self.status})"

    def save(self, *args, **kwargs):
        if self.purpose == OnlinePaymentPurpose.GENERAL:
            if self.bill_id:
                self.purpose = OnlinePaymentPurpose.BILL
            elif self.order_id:
                self.purpose = OnlinePaymentPurpose.ORDER
            elif self.subscription_id:
                self.purpose = OnlinePaymentPurpose.SUBSCRIPTION
        super().save(*args, **kwargs)

    def verify(self, user=None):
        from django.db import transaction as db_transaction
        from django.utils import timezone

        with db_transaction.atomic():
            tx_ref = self.transaction_id or self.gateway_mihpayid or self.gateway_txnid
            tx_method = "payu" if self.payment_gateway == "payu" else "online"

            if self.bill_id and not self.bill_transaction_id:
                self.bill_transaction = Transaction.objects.create(
                    bill=self.bill,
                    amount=self.amount,
                    payment_method=tx_method,
                    transaction_id=tx_ref,
                    notes=(
                        f"PayU payment ({self.gateway_txnid})"
                        if self.payment_gateway == "payu"
                        else f"Verified online payment {self.id}"
                    ),
                )

            if self.order_id:
                from decimal import Decimal
                from orders.models import OrderStatus, PaymentMethod, PaymentStatus

                order = self.order
                prior_verified = (
                    order.online_payments.filter(status=OnlinePaymentStatus.VERIFIED)
                    .exclude(id=self.id)
                    .aggregate(total=Sum("amount"))["total"]
                    or Decimal("0.00")
                )
                total_collected = Decimal(str(prior_verified)) + Decimal(str(self.amount))
                order.amount_collected = total_collected

                if total_collected >= Decimal(str(order.total or 0)):
                    order.payment_status = PaymentStatus.PAID
                elif total_collected > Decimal("0.00"):
                    order.payment_status = PaymentStatus.PARTIAL
                else:
                    order.payment_status = PaymentStatus.PENDING

                order.payment_method = (
                    PaymentMethod.PAYU
                    if self.payment_gateway == "payu"
                    else PaymentMethod.UPI
                )
                if tx_ref:
                    order.payment_transaction_id = tx_ref
                # A verified payment accepts a pending order; later stages are left alone.
                was_pending = order.status == OrderStatus.PENDING
                if was_pending:
                    order.status = OrderStatus.CONFIRMED
                order.save(
                    update_fields=[
                        "status",
                        "payment_status",
                        "payment_method",
                        "amount_collected",
                        "payment_transaction_id",
                    ]
                )
                if was_pending:
                    import threading
                    from django.db import connection
                    order_id_for_route = order.id
                    schema_name = getattr(connection, "schema_name", None)

                    def _add_confirmed_order_to_route():
                        try:
                            from django_tenants.utils import schema_context
                            ctx = schema_context(schema_name) if schema_name else transaction.atomic()
                        except Exception:
                            from contextlib import nullcontext
                            ctx = nullcontext()
                        with ctx:
                            try:
                                from orders.models import Order
                                from orders.services.route_generator import add_order_to_active_route_if_pending
                                confirmed_order = Order.objects.select_related("customer").filter(id=order_id_for_route).first()
                                if confirmed_order:
                                    add_order_to_active_route_if_pending(confirmed_order)
                            except Exception:
                                pass

                    transaction.on_commit(
                        lambda: threading.Thread(target=_add_confirmed_order_to_route, daemon=True).start()
                    )

            self.status = OnlinePaymentStatus.VERIFIED
            if user is not None:
                self.verified_by = user
            self.verified_at = timezone.now()
            self.rejection_reason = ""
            self.save()

            # If a MonthlyBill already exists for the order's or subscription's billing month,
            # automatically re-sync it so prepaid extra orders and subscription payments are reflected.
            from .services import generate_monthly_bill_for_customer

            if self.order_id and self.order and self.order.scheduled_delivery_date:
                dt = self.order.scheduled_delivery_date
                if MonthlyBill.objects.filter(
                    customer=self.customer,
                    billing_month__year=dt.year,
                    billing_month__month=dt.month,
                ).exists():
                    generate_monthly_bill_for_customer(self.customer, dt.year, dt.month)
            elif self.purpose == OnlinePaymentPurpose.SUBSCRIPTION:
                dt = (self.created_at or timezone.now()).date()
                if MonthlyBill.objects.filter(
                    customer=self.customer,
                    billing_month__year=dt.year,
                    billing_month__month=dt.month,
                ).exists():
                    generate_monthly_bill_for_customer(self.customer, dt.year, dt.month)

    def reject(self, user=None, reason=""):
        from django.utils import timezone

        if self.order_id:
            from orders.models import PaymentStatus

            self.order.payment_status = PaymentStatus.FAILED
            self.order.save(update_fields=["payment_status"])

        self.status = OnlinePaymentStatus.REJECTED
        if user is not None:
            self.verified_by = user
        self.verified_at = timezone.now()
        self.rejection_reason = reason
        self.save()


# ───── Auto-Reconciliation signals ─────────────────────────────────────────


@receiver(post_save, sender=Transaction)
def reconcile_on_payment_save(sender, instance, **kwargs):
    """Recalculate the parent bill totals whenever a payment is added or updated."""
    instance.bill.reconcile()


@receiver(post_delete, sender=Transaction)
def reconcile_on_payment_delete(sender, instance, **kwargs):
    """Re-open the parent bill when a payment record is deleted."""
    instance.bill.reconcile()
