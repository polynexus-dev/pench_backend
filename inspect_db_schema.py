import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

cursor = connection.cursor()

# Get columns of orders_route in pench-nagpur
cursor.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'pench-nagpur' AND table_name = 'orders_route'
""")
cols = cursor.fetchall()
print("Columns in 'orders_route':")
for col in cols:
    print(f"  {col[0]}: {col[1]}")
