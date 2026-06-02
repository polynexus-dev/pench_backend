import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from tenants.models import City, Domain, Company

print("=== Companies ===")
for comp in Company.objects.all():
    print(
        f"Company ID: {comp.id} | Name: {comp.name} | Code: {comp.code} | Active: {comp.is_active}"
    )

print("\n=== All Cities (Active & Inactive) ===")
for city in City.objects.all():
    print(
        f"City ID: {city.id} | Name: {city.name} | Schema: {city.schema_name} | Active: {city.is_active}"
    )

print("\n=== Registered Domains ===")
for domain in Domain.objects.all():
    print(
        f"Domain ID: {domain.id} | Domain: {domain.domain} | Tenant: {domain.tenant.schema_name} | Primary: {domain.is_primary}"
    )
