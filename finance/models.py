from django.db import models
from django.db.models import Sum
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from core.models import BaseModel


class BillStatus(models.TextChoices):
    UNPAID = 'unpaid', 'Unpaid'
    PARTIAL = 'partial', 'Partially Paid'
    PAID = 'paid', 'Paid'
    CANCELLED = 'cancelled', 'Cancelled'


class MonthlyBill(BaseModel):
    """
    Summarizes all deliveries for a customer in a specific month.
    """
    customer = models.ForeignKey(
        'crm.Customer',
        on_delete=models.PROTECT,
        related_name='monthly_bills'
    )
    billing_month = models.DateField(help_text="The first day of the month being billed.")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20,
        choices=BillStatus.choices,
        default=BillStatus.UNPAID
    )
    due_date = models.DateField()
    invoice_number = models.CharField(max_length=50, unique=True)
    
    # Optional: PDF Invoice link
    invoice_pdf = models.FileField(upload_to='invoices/', null=True, blank=True)

    class Meta:
        ordering = ['-billing_month']
        unique_together = ('customer', 'billing_month')

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
        total_paid = self.transactions.aggregate(total=Sum('amount'))['total'] or 0
        self.amount_paid = total_paid

        if total_paid <= 0:
            self.status = BillStatus.UNPAID
        elif total_paid >= self.total_amount:
            self.status = BillStatus.PAID
        else:
            self.status = BillStatus.PARTIAL

        self.save(update_fields=['amount_paid', 'status'])


class Transaction(BaseModel):
    """
    Records payments made against bills.
    """
    bill = models.ForeignKey(MonthlyBill, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50, default='online')
    transaction_id = models.CharField(max_length=100, blank=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default='')

    def __str__(self):
        return f"Payment of {self.amount} for {self.bill.invoice_number}"


# ───── Auto-Reconciliation signals ─────────────────────────────────────────

@receiver(post_save, sender=Transaction)
def reconcile_on_payment_save(sender, instance, **kwargs):
    """Recalculate the parent bill totals whenever a payment is added or updated."""
    instance.bill.reconcile()


@receiver(post_delete, sender=Transaction)
def reconcile_on_payment_delete(sender, instance, **kwargs):
    """Re-open the parent bill when a payment record is deleted."""
    instance.bill.reconcile()
