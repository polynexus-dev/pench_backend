import os
import django

# Setup Django Environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context
from tenants.models import City

User = get_user_model()
ACTIVE_SCHEMA = "pench-nagpur"

print("="*60)
print(f"CREATING TEST USERS IN SCHEMA: {ACTIVE_SCHEMA}")
print("="*60)

try:
    city = City.objects.get(schema_name=ACTIVE_SCHEMA)
except City.DoesNotExist:
    print(f"Error: Schema {ACTIVE_SCHEMA} does not exist.")
    # Fallback to the first available city
    city = City.objects.first()
    if city:
        print(f"Falling back to schema: {city.schema_name}")
    else:
        print("Error: No schemas found.")
        city = None

if city:
    with schema_context(city.schema_name):
        # 1. Create ERP Manager
        username_erp = "erp_manager"
        user_erp, created = User.objects.get_or_create(
            username=username_erp,
            defaults={
                "email": "erp@pench.com",
                "phone": "+919000000001",
                "is_erp_user": True,
                "is_staff": True,
                "is_active": True
            }
        )
        user_erp.set_password("password123")
        # Ensure correct flags if it existed
        user_erp.is_erp_user = True
        user_erp.is_staff = True
        user_erp.save()
        print(f"User '{username_erp}' configured. Password: 'password123' | Created: {created}")

        # 2. Create Delivery Driver
        username_driver = "delivery_driver"
        user_driver, created = User.objects.get_or_create(
            username=username_driver,
            defaults={
                "email": "driver@pench.com",
                "phone": "+919000000002",
                "is_driver": True,
                "is_active": True
            }
        )
        user_driver.set_password("password123")
        user_driver.is_driver = True
        user_driver.save()
        print(f"User '{username_driver}' configured. Password: 'password123' | Created: {created}")

        # 3. Create CRM Customer
        username_customer = "crm_customer"
        user_customer, created = User.objects.get_or_create(
            username=username_customer,
            defaults={
                "email": "customer@pench.com",
                "phone": "+919000000003",
                "is_customer": True,
                "is_active": True
            }
        )
        user_customer.set_password("password123")
        user_customer.is_customer = True
        user_customer.save()
        print(f"User '{username_customer}' configured. Password: 'password123' | Created: {created}")

print("="*60)
