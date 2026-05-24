import os
import sys
import django

# Add workspace directory to path
sys.path.insert(0, r"d:\Polynexus\Pench\Backend\pench_backend")

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import User
from django_tenants.utils import schema_context

user = User.objects.filter(username__icontains='pratham').first()
if not user:
    print("User with username/name 'pratham' not found.")
else:
    print(f"User: {user.username}")
    print(f"Full Name: {user.get_full_name()}")
    print(f"is_driver: {user.is_driver}")
    print(f"tenant_schema: {user.tenant_schema}")
    print(f"groups: {list(user.groups.values_list('name', flat=True))}")
    
    schema = 'pench-nagpur'
    with schema_context(schema):
        from orders.models import Route as OrdersRoute
        from orders.serializers import RouteSerializer
        
        # Get active route
        route = OrdersRoute.objects.filter(is_completed=False).order_by('delivery_date').first()
        if route:
            print(f"\nRoute ID: {route.id}")
            print(f"Original Route Status: {route.status}")
            route.status = 'in_progress'
            data = RouteSerializer(route).data
            print("\nSerialized Route Data (when status is in_progress in memory):")
            import json
            print(json.dumps({
                "id": data.get("id"),
                "status": data.get("status"),
                "stops": data.get("stops", [])
            }, indent=2))
        else:
            print("No incomplete route found.")
