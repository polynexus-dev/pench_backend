import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from tenants.models import City, Domain

print("=== Starting Domain Synchronization ===")

base_domains = [
    'localhost',
    'pench.dev.api.polynexus.in',
    'pench.api.polynexus.in'
]

# Add env domain if configured
public_domain = os.environ.get('PUBLIC_DOMAIN')
if public_domain and public_domain not in base_domains:
    base_domains.append(public_domain)

cities = City.objects.exclude(schema_name='public')
created_count = 0

for city in cities:
    subdomain = city.schema_name.replace('_', '-')
    print(f"\nProcessing City: {city.name} (Schema: {city.schema_name})")
    
    # Track existing domains for this city
    existing_domains = {d.domain for d in city.domains.all()}
    
    for base in base_domains:
        domain_name = f"{subdomain}.{base}"
        if domain_name not in existing_domains:
            Domain.objects.create(
                domain=domain_name,
                tenant=city,
                is_primary=False
            )
            print(f" -> REGISTERED: {domain_name}")
            created_count += 1
        else:
            print(f" -> Existing: {domain_name}")

print(f"\n=== Domain Sync Complete! Registered {created_count} missing hostnames ===")
