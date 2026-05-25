import os
import django
import sys

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from django.core.management import call_command

print("=== FORCE RE-MIGRATING DJANGO_CELERY_BEAT IN PUBLIC SCHEMA ===")

connection.set_schema_to_public()
with connection.cursor() as cursor:
    print("Deleting django_celery_beat migration records from public schema...")
    cursor.execute("DELETE FROM django_migrations WHERE app = 'django_celery_beat'")
    
print("Running migrations for django_celery_beat...")
try:
    # We call migrate for django_celery_beat
    call_command('migrate', 'django_celery_beat', schema_name='public')
    print("Migration command completed.")
except Exception as e:
    print(f"Error during migration: {e}")

# Verify if tables now exist
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name LIKE '%crontabschedule%'
    """)
    rows = cursor.fetchall()
    print("Verification query results:")
    for row in rows:
        print(f"  Table: {row[0]}")
