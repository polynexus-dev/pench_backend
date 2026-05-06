from django.db import models
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


class Transaction(BaseModel):
    """
    Records payments made against bills.
    """
    bill = models.ForeignKey(MonthlyBill, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50, default='online')
    transaction_id = models.CharField(max_length=100, blank=True)
    payment_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment of {self.amount} for {self.bill.invoice_number}"
