import os
import sys
import django

sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context
from rest_framework.test import APIRequestFactory, force_authenticate
from accounts.models import User
from crm.models import Customer
from routing.models import Zone
from crm.views import CustomerViewSet

schema_name = "pench_nagpur"
print(f"Running directly under schema: {schema_name}")

with schema_context(schema_name):
    connection.set_schema(schema_name)
    
    # Clean up first
    Customer.objects.filter(phone="9988776655").delete()
    Zone.objects.filter(name="Merge Zone").delete()

    zone = Zone.objects.create(name="Merge Zone", is_active=True)

    primary_cust = Customer.objects.create(
        name="Duplicate Name",
        phone="9988776655",
        email="primary@example.com",
        zone=None,
        location=None,
        trial_approved=False,
        is_new=True,
        is_active=True,
    )

    try:
        from django.contrib.gis.geos import Point
        HAS_GIS_LOCAL = True
    except Exception:
        HAS_GIS_LOCAL = False

    if HAS_GIS_LOCAL:
        dup_loc = Point(79.1, 21.2)
    else:
        dup_loc = {"longitude": 79.1, "latitude": 21.2}

    dup_cust = Customer.objects.create(
        name="Duplicate Name",
        phone="9988776655",
        email="duplicate@example.com",
        zone=zone,
        location=dup_loc,
        trial_approved=True,
        is_new=False,
        is_active=True,
    )

    factory = APIRequestFactory()
    admin_user = User.objects.filter(is_superuser=True).first()
    
    view = CustomerViewSet.as_view({'post': 'sync_refresh_customers'})
    request = factory.post('/api/erp/customers/sync-refresh-customers/', {'dry_run': False})
    force_authenticate(request, user=admin_user)
    
    try:
        response = view(request)
        print("Response Status:", response.status_code)
        print("Response Data:", response.data)
    except Exception as e:
        import traceback
        traceback.print_exc()
