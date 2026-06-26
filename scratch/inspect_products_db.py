from django_tenants.utils import tenant_context
from tenants.models import City
from inventory.models import Product

# Get any existing city to run the query in its schema context
city = City.objects.first()
if city:
    print(f"Inspecting products in schema: {city.schema_name}")
    with tenant_context(city):
        products = Product.objects.all()
        for p in products:
            print(f"Product: {p.name} | SKU: {p.sku} | Unit Price: {p.unit_price} | Unit: {p.unit}")
else:
    print("No cities/tenants found in the public database.")
