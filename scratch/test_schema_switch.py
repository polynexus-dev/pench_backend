import os
import sys
import django

sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context

print("1. schema_name:", connection.schema_name)
with schema_context("pench_nagpur"):
    print("2. schema_name:", connection.schema_name)
    with connection.cursor() as cursor:
        cursor.execute("SHOW search_path")
        print("   search_path:", cursor.fetchone())
print("3. schema_name:", connection.schema_name)
