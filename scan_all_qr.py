import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from crm.models import Customer
from django_tenants.utils import schema_context
from tenants.models import City

target = 'e42c974f-9d3d-4993-a935-de4398612d16'

for city in City.objects.all():
    schema = city.schema_name
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
