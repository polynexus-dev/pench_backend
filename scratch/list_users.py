import os
import django

# Setup Django Environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context
from tenants.models import City

User = get_user_model()

print("="*60)
print("EXTRACTING USERS FROM ACTIVE TENANTS")
print("="*60)

cities = City.objects.all()
for city in cities:
    print(f"\nTenant City Schema: {city.schema_name} ({city.name})")
    print("-" * 50)
    with schema_context(city.schema_name):
        users = User.objects.all()
        if not users.exists():
            print("No users in this schema.")
        for user in users:
            print(f"Username: {user.username:<15} | Email: {user.email:<25} | Is Superuser: {user.is_superuser:<5} | Is Staff: {user.is_staff:<5}")
print("="*60)
