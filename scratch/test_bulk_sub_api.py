import os
import sys
import django

# Add current directory to python path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection, transaction
from django_tenants.utils import schema_context
from rest_framework.test import APIRequestFactory, force_authenticate
from accounts.models import User
from crm.models import Customer
from inventory.models import Product
from subscriptions.models import Subscription
from subscriptions.views import SubscriptionViewSet

schema_name = "pench_nagpur"
print(f"Running comprehensive tests under schema: {schema_name}")

with schema_context(schema_name):
    connection.set_schema(schema_name)
    
    customers = list(Customer.objects.all()[:2])
    products = list(Product.objects.filter(is_active=True)[:2])
    
    if len(customers) < 2 or len(products) < 2:
        print("Not enough customers/products in database for testing!")
        sys.exit(1)
        
    print(f"Customer 1: {customers[0].name} ({customers[0].id})")
    print(f"Customer 2: {customers[1].name} ({customers[1].id})")
    print(f"Product 1: {products[0].name} ({products[0].id})")
    print(f"Product 2: {products[1].name} ({products[1].id})")
    
    admin_user = User.objects.filter(is_superuser=True).first()
    if not admin_user:
        admin_user = User.objects.create_user(
            username="temp_admin_sub_test",
            email="temp_admin_sub_test@example.com",
            password="password123",
            is_erp_user=True,
            tenant_schema=schema_name
        )
        created_admin = True
    else:
        created_admin = False
        
    factory = APIRequestFactory()
    view = SubscriptionViewSet.as_view({'post': 'create'})
    
    try:
        # Scenario A: Flat JSON array with flat product/quantity keys
        print("\n--- Testing Scenario A: Flat JSON array with flat product/quantity keys ---")
        initial_count = Subscription.objects.count()
        payload_a = [
            {
                "customer": str(customers[0].id),
                "frequency": "daily",
                "start_date": "2026-06-06",
                "product": str(products[0].id),
                "quantity": 2
            },
            {
                "customer": str(customers[1].id),
                "frequency": "alternate",
                "start_date": "2026-06-06",
                "product": str(products[1].id),
                "quantity": 3
            }
        ]
        request_a = factory.post('/api/erp/subscriptions/', payload_a, format='json')
        force_authenticate(request_a, user=admin_user)
        response_a = view(request_a)
        
        print("Response Status Code:", response_a.status_code)
        print("Created subscription count increment:", Subscription.objects.count() - initial_count)
        if response_a.status_code == 201:
            print("Successfully processed flat array!")
            
        # Scenario B: Wrapped JSON object containing a 'subscriptions' key
        print("\n--- Testing Scenario B: Wrapped JSON object containing a 'subscriptions' key ---")
        initial_count = Subscription.objects.count()
        payload_b = {
            "subscriptions": [
                {
                    "customer": str(customers[1].id),
                    "frequency": "daily",
                    "start_date": "2026-06-07",
                    "items": [{"product": str(products[1].id), "quantity": 1}]
                },
                {
                    "customer": str(customers[0].id),
                    "frequency": "weekdays",
                    "start_date": "2026-06-07",
                    "product": str(products[0].id),
                    "quantity": 4
                }
            ]
        }
        request_b = factory.post('/api/erp/subscriptions/', payload_b, format='json')
        force_authenticate(request_b, user=admin_user)
        response_b = view(request_b)
        
        print("Response Status Code:", response_b.status_code)
        print("Created subscription count increment:", Subscription.objects.count() - initial_count)
        if response_b.status_code == 201:
            print("Successfully processed wrapped object list!")

        # Scenario C: Single subscription with flat product/quantity mapping
        print("\n--- Testing Scenario C: Single subscription with flat product/quantity mapping ---")
        initial_count = Subscription.objects.count()
        payload_c = {
            "customer": str(customers[1].id),
            "frequency": "weekends",
            "start_date": "2026-06-08",
            "product": str(products[1].id),
            "quantity": 5
        }
        request_c = factory.post('/api/erp/subscriptions/', payload_c, format='json')
        force_authenticate(request_c, user=admin_user)
        response_c = view(request_c)
        
        print("Response Status Code:", response_c.status_code)
        print("Created subscription count increment:", Subscription.objects.count() - initial_count)
        if response_c.status_code == 201:
            print("Successfully processed single subscription with flat fields!")
            
        # Scenario D: Transaction Atomicity (Invalid record in the batch should rollback everything)
        print("\n--- Testing Scenario D: Transaction Atomicity rollback on failure ---")
        initial_count = Subscription.objects.count()
        payload_d = [
            {
                "customer": str(customers[0].id),
                "frequency": "daily",
                "start_date": "2026-06-09",
                "product": str(products[0].id),
                "quantity": 1
            },
            {
                "customer": "invalid-customer-id-that-causes-validation-error",
                "frequency": "alternate",
                "start_date": "2026-06-09",
                "product": str(products[1].id),
                "quantity": 2
            }
        ]
        request_d = factory.post('/api/erp/subscriptions/', payload_d, format='json')
        force_authenticate(request_d, user=admin_user)
        response_d = view(request_d)
        
        print("Response Status Code (Should be 400):", response_d.status_code)
        print("Created subscription count increment (Should be 0 due to rollback):", Subscription.objects.count() - initial_count)
        
    finally:
        if created_admin:
            with schema_context("public"):
                User.objects.filter(username="temp_admin_sub_test").delete()
