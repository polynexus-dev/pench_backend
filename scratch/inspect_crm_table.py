import os
import django
import sys

sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from tenants.models import City, Domain

def main():
    cursor = connection.cursor()
    
    # 1. Get all schemas
    cursor.execute("SELECT schema_name FROM information_schema.schemata;")
    schemas = [r[0] for r in cursor.fetchall()]
    print("Database schemas in PostgreSQL:")
    for s in schemas:
        if not s.startswith("pg_") and s != "information_schema":
            print(f"  - {s}")
            
    # 2. Check for crm_customer table in each schema
    print("\ncrm_customer table status across schemas:")
    for s in schemas:
        if s.startswith("pg_") or s == "information_schema":
            continue
        cursor.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = %s AND table_name = 'crm_customer')",
            [s]
        )
        exists = cursor.fetchone()[0]
        print(f"  Schema '{s}': {exists}")

    # 3. Check City and Domain models in Django
    print("\nCity/Tenant list from Django:")
    for city in City.objects.all():
        print(f"  City: {city.name} (schema: {city.schema_name})")
        domains = Domain.objects.filter(tenant=city)
        for dom in domains:
            print(f"    - Domain: {dom.domain} (primary: {dom.is_primary})")

if __name__ == "__main__":
    main()
