import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

cursor = connection.cursor()

# Get schemas
cursor.execute("SELECT schema_name FROM information_schema.schemata")
schemas = [r[0] for r in cursor.fetchall()]
print(f"All database schemas: {schemas}")

# Look at tables in public
cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
public_tables = [r[0] for r in cursor.fetchall()]
print(f"\nTables in 'public' schema ({len(public_tables)}):")
print(sorted(public_tables))

# Look at tables in pench_nagpur if it exists
if 'pench_nagpur' in schemas:
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'pench_nagpur'")
    nagpur_tables = [r[0] for r in cursor.fetchall()]
    print(f"\nTables in 'pench_nagpur' schema ({len(nagpur_tables)}):")
    print(sorted(nagpur_tables))
else:
    print("\nSchema 'pench_nagpur' does not exist in the database!")
