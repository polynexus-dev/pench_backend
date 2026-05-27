import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django_tenants.utils import schema_context
from accounts.models import User

# Fetch users from tenant
users_to_copy = []
with schema_context('pench_nagpur'):
    users_to_copy = list(User.objects.all())

# Create them in public
with schema_context('public'):
    for u in users_to_copy:
        User.objects.update_or_create(
            username=u.username,
            defaults={
                'password': u.password,
                'phone': u.phone,
                'is_customer': u.is_customer,
                'is_driver': u.is_driver,
                'is_erp_user': u.is_erp_user,
                'tenant_schema': 'pench_nagpur',
                'is_active': True
            }
        )
    print("Successfully copied users to public schema!")
