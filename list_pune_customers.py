import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from crm.models import Customer
from django_tenants.utils import schema_context

with schema_context('pune'):
    customers = Customer.objects.all()
    print(f"Total customers in pune: {customers.count()}")
    for c in customers:
        print(f"{c.id} | {c.qr_code_id}")
