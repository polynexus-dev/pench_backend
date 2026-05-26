import os
import django
import sys

sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context
from tenants.models import City

print("=== INSPECTING BEAT TABLES ===")

# Check public schema
connection.set_schema_to_public()
with connection.cursor() as cursor:
    cursor.execute(
        """
        SELECT table_schema, table_name 
        FROM information_schema.tables 
        WHERE table_name LIKE '%crontabschedule%'
    """
    )
    rows = cursor.fetchall()
    print("Public schema query results:")
    for row in rows:
        print(f"  Schema: {row[0]}, Table: {row[1]}")

# Check other cities
cities = City.objects.exclude(schema_name="public")
for city in cities:
    with schema_context(city.schema_name):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_schema, table_name 
                FROM information_schema.tables 
                WHERE table_name LIKE '%crontabschedule%'
            """
            )
            rows = cursor.fetchall()
            print(f"Schema '{city.schema_name}' query results:")
            for row in rows:
                print(f"  Schema: {row[0]}, Table: {row[1]}")
