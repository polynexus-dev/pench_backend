import os
import django
import sys

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection

print("=== LISTING MIGRATIONS IN PUBLIC SCHEMA ===")
connection.set_schema_to_public()
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT app, name 
        FROM django_migrations 
        ORDER BY app, name
    """)
    rows = cursor.fetchall()
    for row in rows:
        print(f"  App: {row[0]}, Migration: {row[1]}")
