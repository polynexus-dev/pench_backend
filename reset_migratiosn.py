import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

with connection.cursor() as cursor:
    # 1. Reset the schema FIRST
    cursor.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    
    # 2. THEN enable the extension so it lives in the new public schema
    cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    
    print("Database reset and PostGIS enabled successfully.")
