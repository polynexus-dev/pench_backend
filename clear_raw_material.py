import os
import sys
import django

sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import tenant_context
from tenants.models import City

# Fetch all cities (tenants)
cities = City.objects.all()

for city in cities:
    print(
        f"Clearing raw_material_id and deleting stock records in tenant/city: {city.schema_name}"
    )
    try:
        with tenant_context(city):
            with connection.cursor() as cursor:
                # Clear invalid raw material references
                cursor.execute("UPDATE inventory_product SET raw_material_id = NULL;")
                # Delete existing stock and stock movement logs since they referenced products, not raw materials
                cursor.execute("DELETE FROM inventory_stockmovement;")
                cursor.execute("DELETE FROM inventory_stock;")
    except Exception as e:
        print(f"Error on tenant {city.schema_name}: {e}")
print("Successfully cleaned up pre-existing invalid relation data!")
