import os
import sys
import django

# Add current directory to python path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context
from accounts.models import User
from crm.models import Customer

print("--- Querying User in public schema context ---")
with schema_context("public"):
    users = list(User.objects.all())
    print(f"Total Users: {len(users)}")
    for u in users[:5]:
        print(f"User: id={u.id}, username={u.username}, phone={u.phone}, tenant_schema={u.tenant_schema}, is_customer={u.is_customer}")

print("\n--- Querying User in pench_nagpur schema context ---")
with schema_context("pench_nagpur"):
    users = list(User.objects.all())
    print(f"Total Users: {len(users)}")
    for u in users[:5]:
        print(f"User: id={u.id}, username={u.username}, phone={u.phone}, tenant_schema={u.tenant_schema}, is_customer={u.is_customer}")

print("\n--- Querying Customer in pench_nagpur schema context ---")
with schema_context("pench_nagpur"):
    customers = list(Customer.objects.all())
    print(f"Total Customers: {len(customers)}")
    for c in customers[:5]:
        print(f"Customer: id={c.id}, name={c.name}, email={c.email}, phone={c.phone}, user_id={c.user_id}")
