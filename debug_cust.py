import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django_tenants.utils import schema_context
from accounts.models import User

# Fix Akshay jain (User 4)
u4 = User.objects.get(id=4)
with schema_context(u4.tenant_schema):
    from crm.models import Customer
    # Delete duplicate first (has no subs)
    Customer.objects.filter(id="d383a81f-da20-40cf-a48b-8121ed4ca193").delete()
    # Now link real customer to User 4
    Customer.objects.filter(id="23e9a0d5-2234-47ee-baf0-409166887303").update(user_id=4)
    print("Fixed Akshay jain")

# Fix Akshay tadas (User 5)
u5 = User.objects.get(id=5)
with schema_context(u5.tenant_schema):
    from crm.models import Customer
    Customer.objects.filter(id="47af5092-21d7-4521-986f-4cf8e62d6bee").delete()
    Customer.objects.filter(id="fe739ec4-2460-467d-b9c5-7b4a296c2904").update(user_id=5)
    print("Fixed Akshay tadas")

print("Done!")
