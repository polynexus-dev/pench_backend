import os
import django
import sys

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection

print("=== LISTING PUBLIC SCHEMA TABLES ===")
connection.set_schema_to_public()
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    rows = cursor.fetchall()
    for row in rows:
        print(f"  Table: {row[0]}")
