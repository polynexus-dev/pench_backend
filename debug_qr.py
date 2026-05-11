import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from crm.models import Customer
from django_tenants.utils import schema_context
from django.db import models

with schema_context('pune'):
    target = 'e42c974f-9d3d-4993-a935-de4398612d16'
    customers = Customer.objects.filter(qr_code_id=target)
    print(f"Searching for {target}...")
    print(f"Found {customers.count()} customers.")
    for c in customers:
        print(f"ID: {c.id}, Name: {c.name}")
