import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from crm.models import Customer
from django_tenants.utils import schema_context
from tenants.models import City

target = "c4ed832a-4844-42ed-8519-d205283f3b8d"

for city in City.objects.all():
    schema = city.schema_name
    if schema == "public":
        continue
    print(f"Checking schema: {schema}...")
    try:
        with schema_context(schema):
            customers = Customer.objects.filter(qr_code_id=target)
            if customers.exists():
                print(f"  [!] FOUND {customers.count()} customers in {schema}")
                for c in customers:
                    print(f"      ID: {c.id}, Name: {c.name}")
    except Exception as e:
        print(f"  [Error] {e}")
