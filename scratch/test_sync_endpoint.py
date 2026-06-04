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
from crm.views import CustomerViewSet

schema_name = "pench_nagpur"
print(f"Switching to schema context: {schema_name}")

with schema_context(schema_name):
    connection.set_schema(schema_name)
    
    # 1. Create temporary mock data
    print("\n--- Creating Mock Data for Testing ---")
    
    # Mock Customer 1: Has phone/email but no linked User
    mock_phone_cust = "9998887771"
    mock_email_cust = "mock_customer_one@example.com"
    # Ensure they don't already exist
    Customer.objects.filter(phone=mock_phone_cust).delete()
    User.objects.filter(phone=mock_phone_cust).delete()
    
    test_customer = Customer.objects.create(
        name="Test Unique Customer",
        phone=mock_phone_cust,
        email=mock_email_cust,
        address="123 Sync Road"
    )
    print(f"Created Customer: '{test_customer.name}' with phone '{test_customer.phone}' (user={test_customer.user})")
    
    # Mock User 2: Has is_customer=True, tenant_schema=pench_nagpur, but no Customer profile
    mock_phone_user = "9998887772"
    mock_email_user = "mock_user_two@example.com"
    # Ensure they don't already exist
    Customer.objects.filter(phone=mock_phone_user).delete()
    User.objects.filter(phone=mock_phone_user).delete()
    
    test_user = User.objects.create(
        username="mock_user_two",
        phone=mock_phone_user,
        email=mock_email_user,
        first_name="Mock",
        last_name="User Two",
        is_customer=True,
        tenant_schema=schema_name
    )
    test_user.set_unusable_password()
    test_user.save()
    print(f"Created User: '{test_user.username}' with phone '{test_user.phone}' (is_customer={test_user.is_customer}, tenant={test_user.tenant_schema})")
    
    # 2. Setup API client / factory
    factory = APIRequestFactory()
    admin_user = User.objects.filter(is_superuser=True).first() or test_user
    
    # Test GET (dry-run)
    view = CustomerViewSet.as_view({'get': 'sync_refresh_customers'})
    request = factory.get('/api/erp/customers/sync-refresh-customers/?dry_run=true')
    force_authenticate(request, user=admin_user)
    
    print("\n--- Testing GET /api/erp/customers/sync-refresh-customers/ (Dry Run) ---")
    response = view(request)
    print("Response Status:", response.status_code)
    
    if response.status_code == 200:
        data = response.data
        print("Customer -> User Created New (Dry Run):", data['customer_to_user']['created_new_user'])
        print("User -> Customer Created New (Dry Run):", data['user_to_customer']['created_new_customer'])
        
        # Verify lists in details
        print("GET Details - Customer -> User:")
        for det in data['customer_to_user']['details']:
            if det.get('phone') == mock_phone_cust:
                print(f"  Found: {det}")
        
        print("GET Details - User -> Customer:")
        for det in data['user_to_customer']['details']:
            if det.get('phone') == mock_phone_user:
                print(f"  Found: {det}")
                
    # 3. Test POST (Commit sync)
    print("\n--- Testing POST /api/erp/customers/sync-refresh-customers/ (Commit) ---")
    view_post = CustomerViewSet.as_view({'post': 'sync_refresh_customers'})
    request_post = factory.post('/api/erp/customers/sync-refresh-customers/', {'dry_run': False})
    force_authenticate(request_post, user=admin_user)
    
    response_post = view_post(request_post)
    print("Response Status:", response_post.status_code)
    
    if response_post.status_code == 200:
        data_post = response_post.data
        print("Customer -> User Created New (Commit):", data_post['customer_to_user']['created_new_user'])
        print("User -> Customer Created New (Commit):", data_post['user_to_customer']['created_new_customer'])
    
    # 4. Verify post-conditions (checking database directly)
    print("\n--- Verifying Database State After Sync ---")
    connection.set_schema(schema_name)
    
    # Verify test_customer now has a linked user
    updated_cust = Customer.objects.get(id=test_customer.id)
    print(f"Customer '{updated_cust.name}': linked user is '{updated_cust.user.username if updated_cust.user else 'None'}'")
    if updated_cust.user:
        print(f"  User details: phone={updated_cust.user.phone}, is_customer={updated_cust.user.is_customer}, tenant_schema={updated_cust.user.tenant_schema}")
        
    # Verify test_user now has a linked customer profile
    created_cust = Customer.objects.filter(user=test_user).first()
    print(f"User '{test_user.username}': linked customer is '{created_cust.name if created_cust else 'None'}'")
    if created_cust:
        print(f"  Customer details: phone={created_cust.phone}, email={created_cust.email}")
        
    # 5. Clean up mock database records
    print("\n--- Cleaning Up Mock Data ---")
    connection.set_schema(schema_name)
    
    if updated_cust.user:
        updated_cust.user.delete()
    updated_cust.delete()
    
    if created_cust:
        created_cust.delete()
    test_user.delete()
    print("Cleanup completed successfully.")
