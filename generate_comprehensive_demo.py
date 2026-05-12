import os
import django
import random
from datetime import date, datetime, timedelta
from decimal import Decimal

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django_tenants.utils import schema_context
from django.contrib.gis.geos import Point

# Model Imports
from accounts.models import User
from crm.models import Customer
from inventory.models import Product, BottleType, Warehouse, Stock, BottleTransaction, BottleTransactionType
from subscriptions.models import Subscription, SubscriptionItem, DeliveryFrequency
from orders.models import Order, OrderStatus, Route, RouteStop
from finance.models import MonthlyBill, Transaction, BillStatus
from hr.models import Department, Employee, Attendance
from taxation.models import TaxRule, TaxType, TaxCategory, ProductTaxCategory

def generate_demo(schema_name):
    print(f"🚀 Generating COMPLETE Demo Data for: {schema_name}")
    
    try:
        with schema_context(schema_name):
            # --- 1. SETTINGS & TAXATION ---
            tax_sgst, _ = TaxRule.objects.get_or_create(
                name=f"MH SGST 2.5% - {schema_name}", 
                defaults={"state": "Maharashtra", "tax_type": TaxType.SGST, "rate_percentage": 2.5, "effective_from": date(2024, 1, 1)}
            )
            tax_cgst, _ = TaxRule.objects.get_or_create(
                name=f"MH CGST 2.5% - {schema_name}", 
                defaults={"state": "Maharashtra", "tax_type": TaxType.CGST, "rate_percentage": 2.5, "effective_from": date(2024, 1, 1)}
            )
            print("✅ Taxation Rules Created.")

            # --- 2. INVENTORY MASTER ---
            warehouse, _ = Warehouse.objects.get_or_create(
                name=f"{schema_name.capitalize()} Main Hub",
                defaults={"address": f"Central Distribution Center, {schema_name.capitalize()}"}
            )
            
            glass_bottle, _ = BottleType.objects.get_or_create(
                name="1L Glass Bottle", defaults={"deposit_amount": 50.00, "volume_ml": 1000}
            )

            p1, _ = Product.objects.get_or_create(
                sku=f"MILK-A2-1L-{schema_name}",
                defaults={"name": "A2 Cow Milk (1L)", "unit_price": 85.00, "bottle_type": glass_bottle, "is_returnable": True}
            )
            ProductTaxCategory.objects.get_or_create(product=p1, defaults={"tax_category": TaxCategory.ESSENTIAL, "hsn_code": "0401"})
            
            Stock.objects.get_or_create(product=p1, warehouse=warehouse, defaults={"quantity": 500})
            print("✅ Inventory & Stock Created.")

            # --- 3. HR & STAFF ---
            dept, _ = Department.objects.get_or_create(name=f"Logistics - {schema_name}")
            
            # Create a dummy driver user with a unique phone to avoid constraint errors
            driver_username = f"driver_{schema_name}_{random.randint(100,999)}"
            driver_phone = f"9000{random.randint(100000,999999)}"
            
            driver_user = User.objects.create_user(
                username=driver_username,
                password="password123",
                phone=driver_phone,
                first_name="John",
                last_name="Driver",
                is_erp_user=True
            )

            employee = Employee.objects.create(
                user=driver_user,
                department=dept,
                job_title="Senior Driver",
                employee_id=f"EMP-{random.randint(1000,9999)}",
                date_joined=date(2024, 1, 1)
            )
            Attendance.objects.get_or_create(employee=employee, date=date.today())
            print("✅ HR & Staff Data Created.")

            # --- 4. CUSTOMERS & ORDERS ---
            customer, _ = Customer.objects.get_or_create(
                phone=f"982300{random.randint(1000,9999)}",
                defaults={"name": "Amit Kumar", "email": f"amit_{random.randint(1,999)}@{schema_name}.com", "location": Point(73.8567, 18.5204)}
            )
            
            order = Order.objects.create(
                customer=customer,
                scheduled_delivery_date=date.today(),
                status=OrderStatus.PENDING,
                total=85.00,
                delivery_address="Central Area, City"
            )
            print("✅ Customer & Orders Created.")

            # --- 5. LOGISTICS ---
            route = Route.objects.create(
                name=f"Morning Route - {date.today()} - {random.randint(1,99)}",
                delivery_date=date.today(),
                driver=driver_user
            )
            RouteStop.objects.create(route=route, order=order, sequence_number=1)
            print("✅ Delivery Route Created.")

            # --- 6. FINANCE ---
            bill = MonthlyBill.objects.create(
                customer=customer,
                billing_month=date(2024, 5, 1),
                total_amount=2500.00,
                amount_paid=500.00,
                status=BillStatus.PARTIAL,
                due_date=date(2024, 6, 10),
                invoice_number=f"INV-{schema_name}-{random.randint(10000,99999)}"
            )
            Transaction.objects.create(bill=bill, amount=500.00, payment_method="UPI")
            print("✅ Finance & Billing Data Created.")

            # --- 7. BOTTLE TRACKING ---
            BottleTransaction.objects.create(
                bottle_type=glass_bottle,
                customer=customer,
                transaction_type="issued",
                quantity=2,
                recorded_by=driver_user
            )
            print("✅ Bottle Transactions Created.")

            print(f"\n✨ SUCCESS: All demo modules populated for {schema_name}!")

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {str(e)}")

if __name__ == "__main__":
    import sys
    # Usage: python generate_comprehensive_demo.py [schema_name]
    schema = sys.argv[1] if len(sys.argv) > 1 else 'nagpur'
    generate_demo(schema)
