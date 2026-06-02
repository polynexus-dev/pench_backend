import os
import sys
import django

# Add backend directory to sys.path
backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_path not in sys.path:
    sys.path.append(backend_path)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django_tenants.utils import schema_context
from tenants.models import City
from orders.models import Route

for city in City.objects.all():
    schema = city.schema_name
    with schema_context(schema):
        try:
            route = Route.objects.filter(
                id="e5aaf846-e094-45b6-a38a-86c38c7a0972"
            ).first()
            if route:
                print(f"Found route in schema: {schema}! Route name: {route.name}")
        except Exception as e:
            print(f"Error checking schema {schema}: {e}")
