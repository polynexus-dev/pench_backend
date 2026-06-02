import datetime
from django.db import transaction
from django.db.models import Sum
from .models import MonthlyBill, BillStatus
from orders.models import Order, OrderStatus
from crm.models import Customer


def generate_monthly_bill_for_customer(customer, year, month):
    """
    Calculates total for all delivered orders in a month and creates a bill.
    """
    # 1. Define date range
    start_date = datetime.date(year, month, 1)
    if month == 12:
        end_date = datetime.date(year + 1, 1, 1)
    else:
        end_date = datetime.date(year, month + 1, 1)

    # 2. Sum all delivered orders
    stats = Order.objects.filter(
        customer=customer,
        status=OrderStatus.DELIVERED,
        scheduled_delivery_date__gte=start_date,
        scheduled_delivery_date__lt=end_date,
    ).aggregate(total_sum=Sum("total"))

    total_amount = stats["total_sum"] or 0

    if total_amount == 0:
        return None  # No bill needed if nothing delivered

    # 3. Create Bill
    with transaction.atomic():
        invoice_num = f"INV-{customer.id.hex[:6].upper()}-{year}{month:02d}"

        bill, created = MonthlyBill.objects.update_or_create(
            customer=customer,
            billing_month=start_date,
            defaults={
                "total_amount": total_amount,
                "due_date": start_date + datetime.timedelta(days=10),  # Due on 10th
                "invoice_number": invoice_num,
            },
        )
        return bill


def bulk_generate_monthly_bills(year, month):
    """
    Runs for all customers in the current schema.
    """
    customers = Customer.objects.filter(is_active=True)
    generated_count = 0

    for customer in customers:
        bill = generate_monthly_bill_for_customer(customer, year, month)
        if bill:
            generated_count += 1

    return generated_count
