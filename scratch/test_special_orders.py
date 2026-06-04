import os
import sys
import django

# Add current directory to python path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context
from rest_framework.test import APIRequestFactory, force_authenticate
from accounts.models import User
from crm.models import Customer
from inventory.models import Product
from orders.models import Order
from orders.views import OrderViewSet

schema_name = "pench_nagpur"
print(f"Switching to schema context: {schema_name}")

with schema_context(schema_name):
    connection.set_schema(schema_name)
    
    # 1. Setup mock customer, product, and admin user
    print("\n--- Setup Test Data ---")
    admin_user = User.objects.filter(is_superuser=True).first()
    if not admin_user:
        print("ERROR: No superuser found.")
        sys.exit(1)
        
    customer = Customer.objects.filter(is_active=True).first()
    if not customer:
        print("ERROR: No active customer found.")
        sys.exit(1)
        
    product = Product.objects.filter(is_active=True).first()
    if not product:
        print("ERROR: No active product found.")
        sys.exit(1)
        
    print(f"Using Admin: {admin_user.username}")
    print(f"Using Customer: {customer.name} (id: {customer.id})")
    print(f"Using Product: {product.name} (id: {product.id})")
    
    # 2. Setup API Request Factory
    factory = APIRequestFactory()
    
    # Create order payload without subscription (should be treated as special/extra order)
    payload = {
        "customer": customer.id,
        "scheduled_delivery_date": "2026-06-10",
        "delivery_address": "Test Special Delivery Address",
        "items": [
            {
                "product": product.id,
                "quantity": 2
            }
        ]
    }
    
    # 3. Create the order via the ViewSet
    print("\n--- Creating Order without Subscription (Expect is_special=True) ---")
    view_create = OrderViewSet.as_view({'post': 'create'})
    request_create = factory.post('/api/erp/orders/', payload, format='json')
    force_authenticate(request_create, user=admin_user)
    
    response_create = view_create(request_create)
    print("Response Status:", response_create.status_code)
    
    order_id = None
    if response_create.status_code == 201:
        order_data = response_create.data
        order_id = order_data.get("id")
        is_special = order_data.get("is_special")
        print(f"Created Order ID: {order_id}")
        print(f"Is Special flag in response: {is_special}")
        
        # Double check in the database
        db_order = Order.objects.get(id=order_id)
        print(f"Database Order is_special field: {db_order.is_special}")
        if db_order.is_special:
            print("SUCCESS: is_special correctly resolved to True.")
        else:
            print("ERROR: is_special was False in the database!")
    else:
        print("ERROR: Failed to create order. Response:", response_create.data)
        sys.exit(1)
        
    # 4. Test retrieving via special action endpoint
    print("\n--- Retrieving Special Orders Endpoint ---")
    view_special = OrderViewSet.as_view({'get': 'special_orders'})
    request_special = factory.get('/api/erp/orders/special/')
    force_authenticate(request_special, user=admin_user)
    
    response_special = view_special(request_special)
    print("Response Status:", response_special.status_code)
    
    if response_special.status_code == 200:
        special_list = response_special.data
        print(f"Total Special Orders returned: {len(special_list)}")
        
        # Verify our created order is in this list
        found_order = next((o for o in special_list if o.get("id") == order_id), None)
        if found_order:
            print("SUCCESS: Newly created order exists in /api/erp/orders/special/ list.")
            print(f"  Details: ID={found_order['id']}, customer={found_order['customer']}, scheduled_delivery_date={found_order['scheduled_delivery_date']}")
        else:
            print("ERROR: Newly created order was NOT found in the special orders list!")
    else:
        print("ERROR: Failed to fetch special orders. Response:", response_special.data)
        
    # 5. Clean up created order
    print("\n--- Cleaning up Test Data ---")
    if order_id:
        Order.objects.filter(id=order_id).delete()
        print(f"Deleted test order with ID: {order_id}")
    print("Verification completed successfully.")
