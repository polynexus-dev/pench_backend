import datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from .models import MonthlyBill, BillStatus
from orders.models import Order, OrderStatus
from crm.models import Customer


# Packing & Handling Fee Slabs (covers PayU wholesale gateway cost + buffer)
PACKING_AND_HANDLING_SLABS = [
    {"min_amount": Decimal("0.01"), "max_amount": Decimal("1500.00"), "fee": Decimal("5.00"), "label": "Up to INR 1,500 (INR 400 - 1,500)"},
    {"min_amount": Decimal("1500.01"), "max_amount": Decimal("2500.00"), "fee": Decimal("10.00"), "label": "INR 1,500 - INR 2,500"},
    {"min_amount": Decimal("2500.01"), "max_amount": Decimal("4000.00"), "fee": Decimal("18.00"), "label": "INR 2,500 - INR 4,000"},
    {"min_amount": Decimal("4000.01"), "max_amount": None, "fee": Decimal("25.00"), "label": "INR 4,000+"},
]


def get_packing_and_handling_slab(amount):
    """
    Returns {"fee": Decimal, "label": str, "min_amount": float, "max_amount": float|None}
    for any given order/bill amount based on the configured slabs:
      - > 0 to 1,500:   INR 5.00
      - 1,500 to 2,500: INR 10.00
      - 2,500 to 4,000: INR 18.00
      - > 4,000:        INR 25.00
    """
    amt = Decimal(str(amount or 0))
    if amt <= Decimal("0.00"):
        return {
            "fee": Decimal("0.00"),
            "label": "No Handling Fee (INR 0)",
            "min_amount": 0.0,
            "max_amount": 0.0,
        }
    if amt <= Decimal("1500.00"):
        return {
            "fee": Decimal("5.00"),
            "label": "Up to INR 1,500",
            "min_amount": 1.0,
            "max_amount": 1500.0,
        }
    if amt <= Decimal("2500.00"):
        return {
            "fee": Decimal("10.00"),
            "label": "INR 1,500 - INR 2,500",
            "min_amount": 1500.01,
            "max_amount": 2500.0,
        }
    if amt <= Decimal("4000.00"):
        return {
            "fee": Decimal("18.00"),
            "label": "INR 2,500 - INR 4,000",
            "min_amount": 2500.01,
            "max_amount": 4000.0,
        }
    return {
        "fee": Decimal("25.00"),
        "label": "INR 4,000+",
        "min_amount": 4000.01,
        "max_amount": None,
    }


def calculate_packing_and_handling_fee(amount):
    """Returns the Decimal packing & handling fee for the given amount."""
    return get_packing_and_handling_slab(amount)["fee"]


def generate_monthly_bill_for_customer(customer, year, month):
    """
    Calculates total for all delivered orders in a month, applies the Packing & Handling
    slab fee on the unpaid monthly bill amount, and creates/updates the MonthlyBill.
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

    orders_total = Decimal(str(stats["total_sum"] or 0))

    if orders_total == Decimal("0.00"):
        return None  # No bill needed if nothing delivered

    # Calculate payments collected by driver or prepaid online during this period
    payment_stats = Order.objects.filter(
        customer=customer,
        status=OrderStatus.DELIVERED,
        payment_method__in=["cash", "upi", "payu"],
        payment_status__in=["paid", "partial"],
        scheduled_delivery_date__gte=start_date,
        scheduled_delivery_date__lt=end_date,
    ).aggregate(paid_sum=Sum("amount_collected"))

    collected_on_delivery = Decimal(str(payment_stats["paid_sum"] or 0))

    # Calculate Packing & Handling Fee slab on the monthly billable balance
    # (Orders that were already paid at order time already paid their own order-level slab fee)
    billable_for_slab = max(Decimal("0.00"), orders_total - collected_on_delivery)
    bill_handling_fee = calculate_packing_and_handling_fee(billable_for_slab)
    total_amount = orders_total + bill_handling_fee

    # 3. Create Bill
    with transaction.atomic():
        invoice_num = f"INV-{customer.id.hex[:6].upper()}-{year}{month:02d}"

        bill, created = MonthlyBill.objects.update_or_create(
            customer=customer,
            billing_month=start_date,
            defaults={
                "handling_fee": bill_handling_fee,
                "total_amount": total_amount,
                "due_date": start_date + datetime.timedelta(days=10),  # Due on 10th
                "invoice_number": invoice_num,
            },
        )

        if collected_on_delivery > 0:
            from .models import Transaction

            Transaction.objects.update_or_create(
                bill=bill,
                payment_method="cash_upi_delivery",
                defaults={
                    "amount": collected_on_delivery,
                    "notes": f"Aggregated cash/UPI/PayU payments collected on orders for {start_date.strftime('%B %Y')}",
                    "transaction_id": f"COLL-{customer.id.hex[:6].upper()}-{year}{month:02d}",
                },
            )

        # Credit any verified Subscription online payments (PayU or manual UPI) made in this billing month
        from .models import OnlinePayment, OnlinePaymentPurpose, OnlinePaymentStatus, Transaction

        unlinked_sub_payments = OnlinePayment.objects.filter(
            customer=customer,
            purpose=OnlinePaymentPurpose.SUBSCRIPTION,
            status=OnlinePaymentStatus.VERIFIED,
            bill_transaction__isnull=True,
            created_at__date__gte=start_date,
            created_at__date__lt=end_date,
        )
        for sub_payment in unlinked_sub_payments:
            tx_ref = (
                sub_payment.transaction_id
                or sub_payment.gateway_mihpayid
                or sub_payment.gateway_txnid
                or f"SUB-{str(sub_payment.id)[:8].upper()}"
            )
            tx = Transaction.objects.create(
                bill=bill,
                amount=sub_payment.amount,
                payment_method="payu" if sub_payment.payment_gateway == "payu" else "online",
                transaction_id=tx_ref,
                notes=f"Subscription payment credited ({tx_ref})",
            )
            sub_payment.bill = bill
            sub_payment.bill_transaction = tx
            sub_payment.save(update_fields=["bill", "bill_transaction"])

        # Recalculate handling_fee if any subscription prepayments were credited
        sub_prepaid_total = Decimal(
            str(
                OnlinePayment.objects.filter(
                    customer=customer,
                    purpose=OnlinePaymentPurpose.SUBSCRIPTION,
                    status=OnlinePaymentStatus.VERIFIED,
                    bill=bill,
                ).aggregate(s=Sum("amount"))["s"]
                or 0
            )
        )
        effective_unpaid = max(
            Decimal("0.00"), orders_total - collected_on_delivery - sub_prepaid_total
        )
        new_handling_fee = calculate_packing_and_handling_fee(effective_unpaid)
        if new_handling_fee != bill.handling_fee:
            bill.handling_fee = new_handling_fee
            bill.total_amount = orders_total + new_handling_fee
            bill.save(update_fields=["handling_fee", "total_amount"])

        bill.reconcile()
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


def build_monthly_bill_breakdown(bill):
    """
    Builds a comprehensive billing breakdown for an invoice (used by API & PDF):
    1. Weekly subscription delivery attendance (Scheduled vs Skipped/Missed vs Delivered & Charged)
    2. Mid-month additional/extra orders (is_special=True) with item details
    3. Deductions & Credits section (payments made at order time, prepaid subscriptions, bill payments)
    4. Gross Total -> Less Deductions -> Net Payable Balance
    """
    import calendar
    from decimal import Decimal
    from subscriptions.models import Subscription, SubscriptionSkipDate

    customer = bill.customer
    year = bill.billing_month.year
    month = bill.billing_month.month
    last_day = calendar.monthrange(year, month)[1]
    start_date = datetime.date(year, month, 1)
    end_date = (
        datetime.date(year + 1, 1, 1)
        if month == 12
        else datetime.date(year, month + 1, 1)
    )

    all_month_orders = list(
        Order.objects.filter(
            customer=customer,
            scheduled_delivery_date__gte=start_date,
            scheduled_delivery_date__lt=end_date,
        )
        .prefetch_related("items__product")
        .order_by("scheduled_delivery_date", "created_at")
    )

    sub_orders = [o for o in all_month_orders if not o.is_special]
    extra_orders = [
        o for o in all_month_orders if o.is_special and o.status == OrderStatus.DELIVERED
    ]

    # Active/paused subscriptions for customer to check scheduled vs skipped dates
    subs = list(Subscription.objects.filter(customer=customer))
    skip_dates_set = set(
        SubscriptionSkipDate.objects.filter(
            subscription__in=subs,
            skip_date__gte=start_date,
            skip_date__lt=end_date,
        ).values_list("skip_date", flat=True)
    )

    # 1. Weekly Subscription Attendance & Charges
    week_ranges = [
        (1, 7),
        (8, 14),
        (15, 21),
        (22, 28),
    ]
    if last_day > 28:
        week_ranges.append((29, last_day))

    weekly_summary = []
    total_scheduled_days = 0
    total_delivered_days = 0
    total_skipped_days = 0
    subscription_gross_total = Decimal("0.00")

    for idx, (d_start, d_end) in enumerate(week_ranges, start=1):
        w_start = datetime.date(year, month, d_start)
        w_end = datetime.date(year, month, d_end)
        w_sub_orders = [
            o
            for o in sub_orders
            if o.scheduled_delivery_date
            and w_start <= o.scheduled_delivery_date <= w_end
        ]
        delivered_w = [o for o in w_sub_orders if o.status == OrderStatus.DELIVERED]
        non_delivered_w = [
            o for o in w_sub_orders if o.status != OrderStatus.DELIVERED
        ]

        # Count skipped dates in this week that didn't have an order row generated
        order_dates_w = {o.scheduled_delivery_date for o in w_sub_orders}
        skipped_without_order = sum(
            1
            for sd in skip_dates_set
            if w_start <= sd <= w_end and sd not in order_dates_w
        )

        deliv_count = len(delivered_w)
        missed_count = len(non_delivered_w) + skipped_without_order
        sched_count = deliv_count + missed_count

        # If no orders were generated for non-delivered days, estimate scheduled days from subscription frequency
        if sched_count == 0 and subs:
            for day_num in range(d_start, d_end + 1):
                cur_d = datetime.date(year, month, day_num)
                if any(s.start_date <= cur_d and (not s.end_date or s.end_date >= cur_d) for s in subs):
                    sched_count += 1
            missed_count = max(0, sched_count - deliv_count)

        w_charged = sum(
            (Decimal(str(o.total or 0)) for o in delivered_w), Decimal("0.00")
        )
        avg_rate = (
            (w_charged / Decimal(str(deliv_count)))
            if deliv_count > 0
            else Decimal("0.00")
        )

        total_scheduled_days += sched_count
        total_delivered_days += deliv_count
        total_skipped_days += missed_count
        subscription_gross_total += w_charged

        weekly_summary.append(
            {
                "week_number": idx,
                "period": f"{w_start.strftime('%d %b')} - {w_end.strftime('%d %b %Y')}",
                "scheduled_days": sched_count,
                "delivered_days": deliv_count,
                "skipped_or_missed_days": missed_count,
                "rate_per_day": float(round(avg_rate, 2)),
                "charged_amount": float(w_charged),
            }
        )

    # 2. Mid-Month Extra Orders List
    extra_orders_list = []
    extra_orders_gross_total = Decimal("0.00")
    extra_orders_prepaid_total = Decimal("0.00")

    for o in extra_orders:
        o_total = Decimal(str(o.total or 0))
        o_handling = Decimal(str(getattr(o, "handling_fee", 0) or 0))
        o_subtotal = max(Decimal("0.00"), o_total - o_handling)
        o_paid = Decimal(str(o.amount_collected or 0))
        o_rem = o.remaining_amount
        extra_orders_gross_total += o_total
        extra_orders_prepaid_total += o_paid

        items_desc = ", ".join(
            f"{it.product.name} x{int(it.quantity) if it.quantity == int(it.quantity) else it.quantity}"
            for it in o.items.all()
        ) or "Extra Product Order"

        if o.payment_method == "on_account" or o_paid == Decimal("0.00"):
            payment_tag = "Added to Monthly Bill"
        elif o.payment_status == "partial":
            payment_tag = f"Partially Paid ({o.payment_method.upper()})"
        else:
            payment_tag = f"Paid at Order ({o.payment_method.upper()})"

        extra_orders_list.append(
            {
                "id": str(o.id),
                "order_ref": f"ORD-{str(o.id)[:8].upper()}",
                "date": o.scheduled_delivery_date.strftime("%d %b %Y"),
                "items_summary": items_desc,
                "payment_method": o.payment_method,
                "payment_status": o.payment_status,
                "payment_tag": payment_tag,
                "items_subtotal": float(o_subtotal),
                "handling_fee": float(o_handling),
                "total": float(o_total),
                "paid_at_order": float(o_paid),
                "added_to_bill": float(o_rem),
            }
        )

    # 3. Deductions & Credits List
    deductions = []
    for o in extra_orders:
        o_paid = Decimal(str(o.amount_collected or 0))
        if o_paid > Decimal("0.00"):
            deductions.append(
                {
                    "date": o.scheduled_delivery_date.strftime("%d %b %Y"),
                    "type": "Mid-Month Extra Order Payment",
                    "reference": f"ORD-{str(o.id)[:8].upper()} ({o.payment_method.upper()})",
                    "amount": float(o_paid),
                }
            )

    for o in sub_orders:
        if o.status == OrderStatus.DELIVERED:
            o_paid = Decimal(str(o.amount_collected or 0))
            if o_paid > Decimal("0.00"):
                deductions.append(
                    {
                        "date": o.scheduled_delivery_date.strftime("%d %b %Y"),
                        "type": "Subscription Delivery Collection",
                        "reference": f"ORD-{str(o.id)[:8].upper()} ({o.payment_method.upper()})",
                        "amount": float(o_paid),
                    }
                )

    for tx in bill.transactions.all().order_by("payment_date"):
        if tx.payment_method != "cash_upi_delivery":
            deductions.append(
                {
                    "date": tx.payment_date.strftime("%d %b %Y"),
                    "type": (
                        "Prepaid Subscription Credit"
                        if (tx.transaction_id and tx.transaction_id.startswith("SUB-"))
                        or "Subscription" in (tx.notes or "")
                        else f"Bill Payment ({tx.payment_method.upper()})"
                    ),
                    "reference": tx.transaction_id or "N/A",
                    "amount": float(tx.amount),
                }
            )

    bill_handling_fee = Decimal(str(getattr(bill, "handling_fee", 0) or 0))
    billable_for_slab = max(
        Decimal("0.00"),
        (subscription_gross_total + extra_orders_gross_total) - extra_orders_prepaid_total,
    )
    slab_info = get_packing_and_handling_slab(billable_for_slab)
    if bill_handling_fee == Decimal("0.00") and billable_for_slab > Decimal("0.00"):
        bill_handling_fee = slab_info["fee"]

    return {
        "subscription_summary": {
            "total_scheduled_days": total_scheduled_days,
            "total_delivered_days": total_delivered_days,
            "total_skipped_or_missed_days": total_skipped_days,
            "subscription_gross_total": float(subscription_gross_total),
            "weeks": weekly_summary,
        },
        "extra_orders_summary": {
            "count": len(extra_orders_list),
            "extra_orders_gross_total": float(extra_orders_gross_total),
            "extra_orders_prepaid_total": float(extra_orders_prepaid_total),
            "extra_orders_added_to_bill": float(
                extra_orders_gross_total - extra_orders_prepaid_total
            ),
            "orders": extra_orders_list,
        },
        "deductions_and_credits": {
            "total_deductions": float(bill.amount_paid),
            "items": deductions,
        },
        "final_calculation": {
            "subscription_charges": float(subscription_gross_total),
            "mid_month_extra_orders": float(extra_orders_gross_total),
            "packing_and_handling_charges": float(bill_handling_fee),
            "packing_and_handling_slab": slab_info["label"],
            "gross_bill_total": float(bill.total_amount),
            "less_deductions_and_payments": float(bill.amount_paid),
            "net_payable_balance": float(bill.remaining_amount),
        },
    }
