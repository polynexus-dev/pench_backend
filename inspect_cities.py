import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from tenants.models import City, Domain

print("Registered Cities:")
for city in City.objects.all():
    print(f"ID: {city.id}, Name: {city.name}, Schema Name: {city.schema_name}")

print("\nRegistered Domains:")
for domain in Domain.objects.all():
    print(f"Domain: {domain.domain}, Tenant Schema: {domain.tenant.schema_name}")
