import os
import django
import datetime

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django_tenants.utils import schema_context
from orders.models import Order

today = datetime.date.today()
print("Today's date:", today)

with schema_context("nagpur"):
    orders = Order.objects.filter(scheduled_delivery_date=today)
    print(f"Nagpur schema: found {orders.count()} orders for today.")
    for o in orders:
        print(
            f"Order ID: {o.id}, Customer: {o.customer.name}, Status: {o.status}, QR Code ID: {o.customer.qr_code_id}"
        )
