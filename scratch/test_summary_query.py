from django_tenants.utils import tenant_context
from tenants.models import City
from django.db.models import Count
from subscriptions.models import SubscriptionItem, SubscriptionStatus

city = City.objects.first()
if city:
    print(f"Querying in schema: {city.schema_name}")
    with tenant_context(city):
        active_items = SubscriptionItem.objects.filter(
            subscription__status=SubscriptionStatus.ACTIVE
        ).values(
            'subscription__frequency',
            'product__name',
            'product__unit',
            'quantity'
        ).annotate(
            count=Count('id')
        ).order_by('subscription__frequency', 'product__name', 'quantity')
        
        for item in active_items:
            print(item)
else:
    print("No cities/tenants found.")
