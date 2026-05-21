import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django_tenants.utils import schema_context
from tenants.models import City
from crm.models import Customer

target_id = "aa0171c4-c6ee-4552-86af-7d3e0837d523" # Akshay Jain

for city in City.objects.all():
    schema = city.schema_name
    with schema_context(schema):
        try:
            if Customer.objects.filter(id=target_id).exists():
                print(f"FOUND! Customer is in schema: '{schema}'")
        except Exception as e:
            # Table might not exist in some schemas (like public)
            pass
