import os
import sys
import django

# Add current directory to python path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context
from orders.models import Route, RouteStop

with schema_context("pench_nagpur"):
    routes = Route.objects.filter(delivery_date="2026-06-20")
    print(f"Total routes on 2026-06-20: {routes.count()}")
    for r in routes:
        print(f"ID: {r.id}")
        print(f"  Name: {r.name}")
        print(f"  Driver: {r.driver.username if r.driver else 'None'}")
        print(f"  Status: {r.status}")
        print(f"  Is Completed: {r.is_completed}")
        print(f"  Is Test Route: {getattr(r, 'is_test_route', 'N/A')}")
        print(f"  Stops Count: {r.stops.count()}")
        print(f"  Created At: {r.created_at}")
        print("-" * 50)
