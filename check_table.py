import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

cursor = connection.cursor()
cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'pune' AND table_name = 'tracking_driverlocation')")
print(f"Table exists: {cursor.fetchone()[0]}")
