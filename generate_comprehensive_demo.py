import os
import django
import random
from datetime import date, timedelta
from decimal import Decimal

# ─── Django Setup ──────────────────────────────────────────────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django_tenants.utils import schema_context
from django.db import IntegrityError
from django.conf import settings as django_settings

HAS_GIS = getattr(django_settings, 'HAS_GDAL', False)

# ─── Model Imports ─────────────────────────────────────────────────────────────
from accounts.models import User
from crm.models import Customer
from inventory.models import (
    Product, BottleType, Warehouse, Stock,
    BottleTransaction, BottleTransactionType
)
from subscriptions.models import (
    Subscription, SubscriptionItem, SubscriptionSkipDate,
    SubscriptionStatus, DeliveryFrequency
)
from orders.models import Order, OrderStatus, Route, RouteStop
from finance.models import MonthlyBill, Transaction, BillStatus
from hr.models import Department, Employee, Attendance
from taxation.models import TaxRule, TaxType, TaxCategory, ProductTaxCategory


# ─── Helpers ───────────────────────────────────────────────────────────────────

def safe_get_or_create(model, lookup, defaults=None):
    """get_or_create but prints a notice on skip."""
    obj, created = model.objects.get_or_create(**lookup, defaults=defaults or {})
    tag = "  ➕ Created" if created else "  ⏭  Exists"
    print(f"{tag}: {model.__name__} → {obj}")
    return obj, created


def today():
    return date.today()


def make_location(lng, lat):
    """Return a Point or a JSON fallback depending on whether GIS/GDAL is available."""
    if HAS_GIS:
        try:
            from django.contrib.gis.geos import Point
            return Point(lng, lat)
        except Exception:
            pass
    return {"type": "Point", "coordinates": [lng, lat]}


# ─── Main Generator ────────────────────────────────────────────────────────────

def generate_demo(schema_name):
    print(f"\n🚀 Generating COMPLETE Demo Data for schema: [{schema_name}]\n")

    try:
        with schema_context(schema_name):

            # ── 1. TAXATION ───────────────────────────────────────────────────
            print("── 1. Taxation ──")
            tax_sgst, _ = safe_get_or_create(TaxRule,
                lookup={"name": f"MH SGST 2.5% - {schema_name}"},
                defaults={"state": "Maharashtra", "tax_type": TaxType.SGST,
                          "rate_percentage": 2.5, "effective_from": date(2024, 1, 1)}
            )
            tax_cgst, _ = safe_get_or_create(TaxRule,
                lookup={"name": f"MH CGST 2.5% - {schema_name}"},
                defaults={"state": "Maharashtra", "tax_type": TaxType.CGST,
                          "rate_percentage": 2.5, "effective_from": date(2024, 1, 1)}
            )

            # ── 2. INVENTORY ──────────────────────────────────────────────────
            print("\n── 2. Inventory ──")
            warehouse, _ = safe_get_or_create(Warehouse,
                lookup={"name": f"{schema_name.capitalize()} Main Hub"},
                defaults={"address": f"Central Distribution Centre, {schema_name.capitalize()}"}
            )

            glass_bottle, _ = safe_get_or_create(BottleType,
                lookup={"name": "1L Glass Bottle"},
                defaults={"deposit_amount": Decimal("50.00"), "volume_ml": 1000}
            )

            half_bottle, _ = safe_get_or_create(BottleType,
                lookup={"name": "500ml Glass Bottle"},
                defaults={"deposit_amount": Decimal("30.00"), "volume_ml": 500}
            )

            # Products
            p_milk, _ = safe_get_or_create(Product,
                lookup={"sku": f"MILK-A2-1L-{schema_name}"},
                defaults={"name": "A2 Cow Milk (1L)", "unit_price": Decimal("85.00"),
                          "bottle_type": glass_bottle, "is_returnable": True}
            )
            p_curd, _ = safe_get_or_create(Product,
                lookup={"sku": f"CURD-500G-{schema_name}"},
                defaults={"name": "Fresh Curd (500g)", "unit_price": Decimal("45.00"),
                          "bottle_type": half_bottle, "is_returnable": True}
            )
            p_ghee, _ = safe_get_or_create(Product,
                lookup={"sku": f"GHEE-500G-{schema_name}"},
                defaults={"name": "Pure Desi Ghee (500g)", "unit_price": Decimal("320.00"),
                          "is_returnable": False}
            )

            # Tax categories
            for prod in [p_milk, p_curd, p_ghee]:
                ProductTaxCategory.objects.get_or_create(
                    product=prod,
                    defaults={"tax_category": TaxCategory.ESSENTIAL, "hsn_code": "0401"}
                )

            # Stock
            for prod in [p_milk, p_curd, p_ghee]:
                Stock.objects.get_or_create(
                    product=prod, warehouse=warehouse,
                    defaults={"quantity": 500}
                )

            # ── 3. HR & STAFF ─────────────────────────────────────────────────
            print("\n── 3. HR & Staff ──")
            dept, _ = safe_get_or_create(Department,
                lookup={"name": f"Logistics - {schema_name}"}
            )

            # Create driver (skip gracefully if username taken)
            driver_user = None
            for attempt in range(5):
                driver_username = f"driver_{schema_name}_{random.randint(1000, 9999)}"
                driver_phone   = f"90{random.randint(10000000, 99999999)}"
                driver_email   = f"{driver_username}@{schema_name}.demo"
                try:
                    driver_user = User.objects.create_user(
                        username=driver_username,
                        password="password123",
                        phone=driver_phone,
                        email=driver_email,
                        first_name="Raju",
                        last_name="Delivery",
                        is_erp_user=True,
                        is_driver=True,
                    )
                    print(f"  ➕ Created: User (driver) → {driver_user.username}")
                    break
                except IntegrityError:
                    continue

            if driver_user:
                emp_id = f"EMP-{schema_name[:3].upper()}-{random.randint(1000, 9999)}"
                emp, _ = safe_get_or_create(Employee,
                    lookup={"employee_id": emp_id},
                    defaults={"user": driver_user, "department": dept,
                              "job_title": "Senior Driver", "date_joined": date(2024, 1, 1)}
                )
                Attendance.objects.get_or_create(employee=emp, date=today())

            # ── 4. CUSTOMERS ──────────────────────────────────────────────────
            print("\n── 4. Customers ──")

            customer_profiles = [
                {
                    "name": "Amit Kumar",
                    "phone": f"9823{random.randint(100000,999999)}",
                    "email": f"amit_{random.randint(1,9999)}@{schema_name}.demo",
                    "address": "Plot 12, Dharampeth, Nagpur",
                    "location": make_location(79.0882, 21.1458),
                    # Subscription: daily milk
                    "sub_freq": DeliveryFrequency.DAILY,
                    "sub_items": [(p_milk, 2)],
                    "vacation": None,
                    "skip_offset": None,
                },
                {
                    "name": "Priya Sharma",
                    "phone": f"9765{random.randint(100000,999999)}",
                    "email": f"priya_{random.randint(1,9999)}@{schema_name}.demo",
                    "address": "Flat 3, Civil Lines, Nagpur",
                    "location": make_location(79.0764, 21.1497),
                    # Subscription: alternate day milk + curd
                    "sub_freq": DeliveryFrequency.ALTERNATE,
                    "sub_items": [(p_milk, 1), (p_curd, 1)],
                    "vacation": (today() + timedelta(days=3), today() + timedelta(days=10)),
                    "skip_offset": None,
                },
                {
                    "name": "Suresh Patel",
                    "phone": f"9876{random.randint(100000,999999)}",
                    "email": f"suresh_{random.randint(1,9999)}@{schema_name}.demo",
                    "address": "Bungalow 7, Wardha Road, Nagpur",
                    "location": make_location(79.1010, 21.1321),
                    # Subscription: weekdays only milk + ghee
                    "sub_freq": DeliveryFrequency.WEEKDAYS,
                    "sub_items": [(p_milk, 3), (p_ghee, 1)],
                    "vacation": None,
                    "skip_offset": 5,   # Skip delivery 5 days from today
                },
                {
                    "name": "Kavita Deshmukh",
                    "phone": f"9988{random.randint(100000,999999)}",
                    "email": f"kavita_{random.randint(1,9999)}@{schema_name}.demo",
                    "address": "Row House 9, Ramdaspeth, Nagpur",
                    "location": make_location(79.0804, 21.1558),
                    # Subscription: custom days (Mon, Wed, Fri) = [0, 2, 4]
                    "sub_freq": DeliveryFrequency.CUSTOM,
                    "sub_items": [(p_milk, 1), (p_curd, 2)],
                    "vacation": None,
                    "skip_offset": None,
                },
            ]

            customers = []
            subscriptions_created = []

            for profile in customer_profiles:
                # Customer
                cust, _ = safe_get_or_create(Customer,
                    lookup={"email": profile["email"]},
                    defaults={
                        "name": profile["name"],
                        "phone": profile["phone"],
                        "address": profile["address"],
                        "location": profile["location"],
                    }
                )
                customers.append(cust)

                # ── 5. SUBSCRIPTIONS ──────────────────────────────────────────
                # One sub per customer (skip if already exists for this customer+frequency)
                existing_sub = Subscription.objects.filter(
                    customer=cust, frequency=profile["sub_freq"]
                ).first()

                if existing_sub:
                    print(f"  ⏭  Exists: Subscription ({profile['sub_freq']}) for {cust.name}")
                    sub = existing_sub
                else:
                    sub_kwargs = dict(
                        customer=cust,
                        status=SubscriptionStatus.ACTIVE,
                        frequency=profile["sub_freq"],
                        start_date=today() - timedelta(days=30),
                        delivery_address=profile["address"],
                        special_instructions="Please ring the bell.",
                    )
                    if profile["sub_freq"] == DeliveryFrequency.CUSTOM:
                        sub_kwargs["custom_days"] = [0, 2, 4]   # Mon, Wed, Fri

                    # Vacation/pause
                    if profile["vacation"]:
                        sub_kwargs["is_paused"] = True
                        sub_kwargs["pause_start"] = profile["vacation"][0]
                        sub_kwargs["pause_end"]   = profile["vacation"][1]

                    sub = Subscription.objects.create(**sub_kwargs)
                    print(f"  ➕ Created: Subscription ({profile['sub_freq']}) for {cust.name}")

                    # Subscription items
                    for product, qty in profile["sub_items"]:
                        SubscriptionItem.objects.get_or_create(
                            subscription=sub, product=product,
                            defaults={"quantity": qty}
                        )

                    # Skip date
                    if profile["skip_offset"]:
                        skip_day = today() + timedelta(days=profile["skip_offset"])
                        SubscriptionSkipDate.objects.get_or_create(
                            subscription=sub, skip_date=skip_day,
                            defaults={"reason": "Customer requested skip"}
                        )
                        print(f"    ➕ Skip date added: {skip_day}")

                subscriptions_created.append(sub)

            # ── 6. ORDERS — past 7 days with varied statuses ──────────────────
            print("\n── 6. Orders (last 7 days, varied statuses) ──")

            # Status cycle to give the calendar varied data
            status_cycle = [
                OrderStatus.DELIVERED,
                OrderStatus.DELIVERED,
                OrderStatus.IN_TRANSIT,
                OrderStatus.PENDING,
                OrderStatus.CANCELLED,
                OrderStatus.DELIVERED,
                OrderStatus.CONFIRMED,
            ]

            all_orders = []
            for i, (cust, sub) in enumerate(zip(customers, subscriptions_created)):
                for day_offset in range(-6, 1):   # -6 days ago → today
                    delivery_day = today() + timedelta(days=day_offset)
                    # Respect frequency — skip off-days
                    if not sub.should_deliver_on(delivery_day):
                        continue
                    # Skip if order already exists for this sub+date
                    if Order.objects.filter(subscription=sub, scheduled_delivery_date=delivery_day).exists():
                        continue

                    order_status = status_cycle[(i + abs(day_offset)) % len(status_cycle)]
                    items = sub.items.select_related('product').all()
                    total = sum(it.product.unit_price * it.quantity for it in items)

                    order = Order.objects.create(
                        customer=cust,
                        subscription=sub,
                        scheduled_delivery_date=delivery_day,
                        status=order_status,
                        delivery_address=sub.delivery_address or cust.address,
                        delivery_notes=sub.special_instructions,
                        total=total,
                    )
                    from orders.models import OrderItem
                    for it in items:
                        OrderItem.objects.get_or_create(
                            order=order, product=it.product,
                            defaults={"quantity": it.quantity, "unit_price": it.product.unit_price}
                        )
                    all_orders.append(order)

            print(f"  ➕ Created {len(all_orders)} orders across {len(customers)} customers.")

            # ── 7. LOGISTICS ROUTE ────────────────────────────────────────────
            print("\n── 7. Logistics Route ──")
            if driver_user:
                route = Route.objects.create(
                    name=f"Morning Route - {today()} #{random.randint(1,99)}",
                    delivery_date=today(),
                    driver=driver_user
                )
                # Attach today's orders to route stops
                todays_orders = [o for o in all_orders if o.scheduled_delivery_date == today()]
                for seq, order in enumerate(todays_orders[:10], start=1):   # max 10 stops
                    if not hasattr(order, 'route_stop'):
                        RouteStop.objects.get_or_create(route=route, order=order, defaults={"sequence_number": seq})
                print(f"  ➕ Created Route with {len(todays_orders[:10])} stops.")

            # ── 8. FINANCE ────────────────────────────────────────────────────
            print("\n── 8. Finance & Billing ──")
            for cust in customers:
                inv_no = f"INV-{schema_name[:3].upper()}-{random.randint(10000,99999)}"
                bill, created = MonthlyBill.objects.get_or_create(
                    customer=cust,
                    billing_month=date(today().year, today().month, 1),
                    defaults={
                        "total_amount": Decimal("2550.00"),
                        "amount_paid": Decimal("1000.00"),
                        "status": BillStatus.PARTIAL,
                        "due_date": today() + timedelta(days=10),
                        "invoice_number": inv_no,
                    }
                )
                if created:
                    Transaction.objects.create(bill=bill, amount=Decimal("1000.00"), payment_method="UPI")
                    print(f"  ➕ Created Bill + Transaction for {cust.name}")
                else:
                    print(f"  ⏭  Exists: Bill for {cust.name}")

            # ── 9. BOTTLE TRANSACTIONS ────────────────────────────────────────
            print("\n── 9. Bottle Tracking ──")
            for cust in customers:
                BottleTransaction.objects.create(
                    bottle_type=glass_bottle,
                    customer=cust,
                    transaction_type=BottleTransactionType.ISSUED,
                    quantity=2,
                    recorded_by=driver_user if driver_user else None
                )
            print(f"  ➕ Issued bottles to {len(customers)} customers.")

            # ── SUMMARY ───────────────────────────────────────────────────────
            print(f"\n{'─'*55}")
            print(f"✨ SUCCESS: All demo modules populated for [{schema_name}]!")
            print(f"   • {len(customers)} customers")
            print(f"   • {len(subscriptions_created)} subscriptions "
                  f"(daily / alternate / weekdays / custom)")
            print(f"   • {len(all_orders)} orders with varied statuses "
                  f"(delivered / in_transit / pending / cancelled)")
            print(f"   • 1 vacation-paused subscription (Priya Sharma)")
            print(f"   • 1 skip-date subscription (Suresh Patel)")
            print(f"{'─'*55}\n")

    except Exception as e:
        import traceback
        print(f"\n❌ CRITICAL ERROR: {str(e)}")
        traceback.print_exc()


if __name__ == "__main__":
    import sys
    # Usage: python generate_comprehensive_demo.py [schema_name]
    schema = sys.argv[1] if len(sys.argv) > 1 else "nagpur"
    generate_demo(schema)
