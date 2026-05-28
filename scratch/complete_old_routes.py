import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

import datetime
from django_tenants.utils import schema_context, get_tenant_model
from django.utils import timezone

TenantModel = get_tenant_model()
today = datetime.date.today()

for tenant in TenantModel.objects.exclude(schema_name='public'):
    with schema_context(tenant.schema_name):
        from orders.models import Route
        from routing.models import Driver

        # 1. Mark all old incomplete routes as completed
        stale = Route.objects.filter(is_completed=False, delivery_date__lt=today)
        count = stale.count()
        if count > 0:
            stale.update(is_completed=True, status='completed', completed_at=timezone.now())
            print(f'[{tenant.schema_name}] Marked {count} old routes as completed.')

        # 2. Reset any drivers stuck in on_trip state
        stuck_drivers = Driver.objects.filter(on_trip=True)
        d_count = stuck_drivers.count()
        if d_count > 0:
            stuck_drivers.update(on_trip=False, is_available=True)
            print(f'[{tenant.schema_name}] Reset {d_count} stuck drivers.')

        if count == 0 and d_count == 0:
            print(f'[{tenant.schema_name}] No stale routes or stuck drivers.')

print("\nDone!")
