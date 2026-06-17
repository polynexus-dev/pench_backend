import os
import sys
import django

sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context
from orders.models import DeliveryLog

schema = "pench_nagpur"
print(f"--- DELIVERY LOGS FOR SCHEMA: {schema} ---")

with schema_context(schema):
    connection.set_schema(schema)
    logs = DeliveryLog.objects.all().order_by('-timestamp')[:50]
    print(f"Total Logs fetched: {len(logs)}")
    for log in logs:
        print(f"[{log.timestamp}] Action: {log.action}")
        print(f"  Details: {log.details}")
        print("-" * 50)
