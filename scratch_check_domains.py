import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from tenants.models import City
from django_tenants.utils import schema_context

for city in City.objects.all():
    print(f"City: {city.name}, Schema: {city.schema_name}")
    for domain in city.domains.all():
        print(f"  Domain: {domain.domain}, Primary: {domain.is_primary}")
