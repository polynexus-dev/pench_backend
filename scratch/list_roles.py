import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context
from tenants.models import City

User = get_user_model()

print("=" * 80)
print("USER ROLES & PROFILES IN SCHEMAS")
print("=" * 80)

cities = City.objects.all()
for city in cities:
    print(f"\nCity Schema: {city.schema_name} ({city.name})")
    print("-" * 50)
    with schema_context(city.schema_name):
        users = User.objects.all()
        for user in users:
            roles = []
            if user.is_superuser:
                roles.append("Superuser")
            if user.is_erp_user:
                roles.append("ERP User")
            if user.is_driver:
                roles.append("Driver")
            if user.is_customer:
                roles.append("Customer")

            roles_str = ", ".join(roles) if roles else "No Role"
            print(
                f"Username: {user.username:<15} | Roles: {roles_str:<30} | Phone: {user.phone:<15}"
            )
print("=" * 80)
