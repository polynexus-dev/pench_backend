import os
import sys
import django

# Add current directory to python path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context
from crm.models import Customer
from crm.views import CustomerViewSet
from rest_framework.test import APIRequestFactory

factory = APIRequestFactory()
request = factory.get('/')

schema_name = "pench_nagpur"
with schema_context(schema_name):
    connection.set_schema(schema_name)
    customer = Customer.objects.first()
    if customer:
        viewset = CustomerViewSet()
        # Mock request.tenant
        from tenants.models import City
        city = City.objects.filter(schema_name=schema_name).first()
        request.tenant = city
        
        canvas = viewset._generate_qr_label_image(request, customer)
        
        # Save image inside artifacts/scratch directory
        output_dir = os.path.dirname(__file__)
        output_path = os.path.join(output_dir, "test_qr_label.png")
        canvas.save(output_path, format="PNG")
        print(f"Successfully generated mock QR label at: {output_path}")
    else:
        print("No customers found in Nagpur schema.")
