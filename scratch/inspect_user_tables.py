import os
import sys
import django

# Add current directory to python path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context

cursor = connection.cursor()

# Check schemas
cursor.execute("SELECT schema_name FROM tenants_city")
schemas = [r[0] for r in cursor.fetchall()]
print("Available schemas:", schemas)

# Check which schemas have accounts_user table
for schema in schemas + ["public"]:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = %s AND table_name = 'accounts_user'
        )
        """,
        [schema],
    )
    exists = cursor.fetchone()[0]
    print(f"Schema '{schema}' has accounts_user table: {exists}")
