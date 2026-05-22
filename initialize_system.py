import os
import django
import sys

# Set up Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from tenants.models import City, Domain, Company
from accounts.models import User
from django_tenants.utils import schema_context
from django.db import connection

print("=== STARTING SYSTEM INITIALIZATION ===")

# 1. Create Company
company, created = Company.objects.get_or_create(
    code='polynexus',
    defaults={'name': 'Polynexus Dev', 'is_active': True}
)
print(f"Company polynexus: {'CREATED' if created else 'EXISTS'}")

# 2. Create Public Tenant
public_tenant = City.objects.filter(schema_name='public').first()
if not public_tenant:
    public_tenant = City.objects.create(
        schema_name='public',
        name='Public',
        state='National',
        code='pub',
        company=company,
        is_active=True
    )
    print("Created public tenant")
else:
    print("Public tenant already exists")

# 3. Create Public Domains
Domain.objects.get_or_create(domain='localhost', defaults={'tenant': public_tenant, 'is_primary': True})
Domain.objects.get_or_create(domain='127.0.0.1', defaults={'tenant': public_tenant, 'is_primary': False})
print("Public domains registered")

# 4. Create Tenant Cities (schemas)
tenants_to_create = [
    ('nagpur', 'Nagpur', 'nagpur.localhost', 'MH', 'NAG'),
    ('pench-nagpur', 'Pench Nagpur', 'pench-nagpur.localhost', 'MH', 'PNAG'),
    ('pune', 'Pune', 'pune.localhost', 'MH', 'PUN')
]

for schema_name, name, domain_name, state, code in tenants_to_create:
    tenant = City.objects.filter(schema_name=schema_name).first()
    if not tenant:
        print(f"Creating tenant schema '{schema_name}'...")
        tenant = City.objects.create(
            schema_name=schema_name,
            name=name,
            state=state,
            code=code,
            company=company,
            is_active=True
        )
        print(f"Tenant schema '{schema_name}' created successfully")
    else:
        print(f"Tenant schema '{schema_name}' already exists")

    # Register domain for tenant
    Domain.objects.get_or_create(
        domain=domain_name,
        defaults={'tenant': tenant, 'is_primary': True}
    )
    # Also register extra local test domains
    Domain.objects.get_or_create(
        domain=f"{schema_name}-new.localhost",
        defaults={'tenant': tenant, 'is_primary': False}
    )
    print(f"Domains registered for '{schema_name}'")

# 5. Create Superuser in public schema (accounts app is shared)
admin_username = 'admin'
admin_email = 'admin@dairy.com'
admin_password = 'admin' # The password you use to login in the local front-end

admin_user = User.objects.filter(username=admin_username).first()
if not admin_user:
    print("Creating superuser...")
    admin_user = User.objects.create_superuser(
        username=admin_username,
        email=admin_email,
        password=admin_password,
        first_name='Super',
        last_name='Admin',
        phone='9999999999',
        is_erp_user=True
    )
    print("Superuser created successfully!")
else:
    # Make sure details/permissions are updated
    admin_user.is_superuser = True
    admin_user.is_staff = True
    admin_user.is_erp_user = True
    admin_user.set_password(admin_password)
    admin_user.save()
    print("Superuser password reset and flags verified")

print("\n=== SYSTEM INITIALIZATION COMPLETED ===")
