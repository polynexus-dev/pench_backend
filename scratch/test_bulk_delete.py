import os
import sys
import django
import datetime

# Add current directory to python path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection, transaction
from django_tenants.utils import schema_context
from accounts.models import User
from crm.models import Customer
from inventory.models import Product
from subscriptions.models import Subscription, SubscriptionItem
from orders.models import Order, OrderItem
from finance.models import MonthlyBill

schema_name = "pench_nagpur"
print(f"Running test on schema: {schema_name}")
connection.set_schema(schema_name)

# Clean up first
Customer.objects.filter(email="delete_test@example.com").delete()
User.objects.filter(username="temp_delete_test_user").delete()

# 1. Create mock data
print("Creating mock customer and dependencies...")
user = User.objects.create_user(
    username="temp_delete_test_user",
    email="delete_test@example.com",
    password="password123",
    is_customer=True,
    tenant_schema=schema_name
)

connection.set_schema(schema_name)

# Print schema info before query
with connection.cursor() as cursor:
    cursor.execute("SHOW search_path")
    print("[DEBUG] connection.schema_name:", connection.schema_name)
    print("[DEBUG] Database search_path:", cursor.fetchone())
    
# Check if a customer profile was auto-created by signals
customer = Customer.objects.filter(user=user).first()
if not customer:
    customer = Customer.objects.create(
        name="Temp Delete Customer",
        user=user,
        email="delete_test@example.com"
    )
    
print(f"Customer created: {customer.name} ({customer.id})")

# Create subscription
product = Product.objects.filter(is_active=True).first()
if not product:
    product = Product.objects.create(name="Temp Product", sku="TMP-PROD", unit_price=10.0)
    
subscription = Subscription.objects.create(
    customer=customer,
    start_date=datetime.date.today()
)
SubscriptionItem.objects.create(
    subscription=subscription,
    product=product,
    quantity=3
)
print(f"Subscription created: {subscription.id}")

# Create order
order = Order.objects.create(
    customer=customer,
    subscription=subscription,
    scheduled_delivery_date=datetime.date.today(),
    delivery_address="Address"
)
OrderItem.objects.create(
    order=order,
    product=product,
    quantity=3,
    unit_price=product.unit_price
)
print(f"Order created: {order.id}")

# Create monthly bill
monthly_bill = MonthlyBill.objects.create(
    customer=customer,
    billing_month=datetime.date.today().replace(day=1),
    due_date=datetime.date.today(),
    invoice_number="INV-TEMP-999"
)
print(f"MonthlyBill created: {monthly_bill.id}")

# 2. Run the deletion logic
print("\n--- Running bulk delete logic ---")

customer_ids = [str(customer.id)]

try:
    with transaction.atomic():
        # Fetch customers
        customers_qs = Customer.objects.filter(id__in=customer_ids)
        user_ids = list(customers_qs.exclude(user__isnull=True).values_list("user_id", flat=True))
        
        # Delete orders (protected)
        order_del_count, _ = Order.objects.filter(customer__in=customers_qs).delete()
        print(f"Deleted {order_del_count} orders.")
        
        # Delete bills (protected)
        bill_del_count, _ = MonthlyBill.objects.filter(customer__in=customers_qs).delete()
        print(f"Deleted {bill_del_count} monthly bills.")
        
        # Delete customers (cascades subscriptions, balances, prices)
        cust_del_count, _ = customers_qs.delete()
        print(f"Deleted {cust_del_count} customer profiles.")
        
        # Delete associated users
        if user_ids:
            user_del_count, _ = User.objects.filter(id__in=user_ids).delete()
            print(f"Deleted {user_del_count} users.")
            
    print("\nDeletion completed successfully without error!")
    
    # Verify database cleanup
    print("\nVerifying database state:")
    print(f"Customer exists? {Customer.objects.filter(id=customer.id).exists()}")
    print(f"User exists? {User.objects.filter(username='temp_delete_test_user').exists()}")
    print(f"Subscription exists? {Subscription.objects.filter(id=subscription.id).exists()}")
    print(f"Order exists? {Order.objects.filter(id=order.id).exists()}")
    print(f"MonthlyBill exists? {MonthlyBill.objects.filter(id=monthly_bill.id).exists()}")
    
except Exception as e:
    import traceback
    print("\nDeletion failed!")
    traceback.print_exc()

