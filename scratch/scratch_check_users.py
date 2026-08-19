import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import User
from django_tenants.utils import schema_context
from crm.models import Customer
from routing.models import Driver

print("=== PUBLIC USERS ===")
for u in User.objects.all():
    print(f"ID: {u.id}, Username: {u.username}, Phone: {u.phone}, Email: {u.email}, is_customer: {u.is_customer}, is_driver: {u.is_driver}, is_erp: {u.is_erp_user}, tenant_schema: {u.tenant_schema}")

print("\n=== NAGPUR CUSTOMERS ===")
with schema_context('nagpur'):
    for c in Customer.objects.all()[:10]:
        print(f"ID: {c.id}, Name: {c.name}, Phone: {c.phone}, User: {c.user}")
    for d in Driver.objects.all():
        print(f"Driver ID: {d.id}, Name: {d.name}, Phone: {d.phone}, User: {d.user}")

print("\n=== PUNE CUSTOMERS ===")
with schema_context('pune'):
    for c in Customer.objects.all()[:10]:
        print(f"ID: {c.id}, Name: {c.name}, Phone: {c.phone}, User: {c.user}")
    for d in Driver.objects.all():
        print(f"Driver ID: {d.id}, Name: {d.name}, Phone: {d.phone}, User: {d.user}")
