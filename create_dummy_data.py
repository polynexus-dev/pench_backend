import os
import django
import random
from decimal import Decimal

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django_tenants.utils import schema_context
from crm.models import Customer
from inventory.models import Product, BottleType, Warehouse
from subscriptions.models import Subscription, SubscriptionItem, DeliveryFrequency
from django.contrib.gis.geos import Point

def create_dummy_data(schema_name):
    print(f"--- Creating dummy data for schema: {schema_name} ---")
    
    with schema_context(schema_name):
        # 1. Create Warehouse
        warehouse, _ = Warehouse.objects.get_or_create(
            name="Main Pune Hub",
            address="Kothrud Depot, Pune"
        )
        
        # 2. Create Bottle Type
        bottle, _ = BottleType.objects.get_or_create(
            name="1L Glass Bottle",
            deposit_amount=50.00,
            volume_ml=1000
        )
        
        # 3. Create Products
        p1, _ = Product.objects.get_or_create(
            sku="MILK-A2-1L",
            defaults={
                "name": "A2 Cow Milk (1L)",
                "unit_price": 85.00,
                "unit": "Litre",
                "is_returnable": True,
                "bottle_type": bottle
            }
        )
        
        p2, _ = Product.objects.get_or_create(
            sku="PANEER-500G",
            defaults={
                "name": "Fresh Paneer (500g)",
                "unit_price": 250.00,
                "unit": "Pack"
            }
        )

        # 4. Create Customers with GPS Coordinates (Kothrud, Pune area)
        # Base: 18.5074, 73.8077
        locations = [
            (18.5074, 73.8077), (18.5085, 73.8090), (18.5060, 73.8100),
            (18.5090, 73.8120), (18.5040, 73.8060), (18.5100, 73.8050),
            (18.5055, 73.8085), (18.5070, 73.8115), (18.5110, 73.8095),
            (18.5030, 73.8070)
        ]
        
        names = ["Amit Sharma", "Priya Patil", "Rahul Deshpande", "Sneha Kulkarni", 
                 "Vikram Joshi", "Anjali Mane", "Sagar Shinde", "Deepa Gokhale",
                 "Nitin More", "Swati Gadgil"]

        for i in range(10):
            email = f"customer{i+1}@{schema_name}.com"
            lat, lng = locations[i]
            
            customer, created = Customer.objects.get_or_create(
                email=email,
                defaults={
                    "name": names[i],
                    "phone": f"982300000{i}",
                    "address": f"Flat {101+i}, Tower {chr(65+i)}, Kothrud, Pune",
                    "location": Point(lng, lat) # Point takes (x, y) which is (lng, lat)
                }
            )
            
            if created:
                print(f"Created Customer: {customer.name} at {lat}, {lng}")
                
                # 5. Create Subscriptions for each customer
                sub = Subscription.objects.create(
                    customer=customer,
                    frequency=DeliveryFrequency.DAILY,
                    start_date="2024-05-01",
                    delivery_address=customer.address
                )
                
                SubscriptionItem.objects.create(
                    subscription=sub,
                    product=p1,
                    quantity=random.randint(1, 3)
                )
                
                if random.choice([True, False]):
                    SubscriptionItem.objects.create(
                        subscription=sub,
                        product=p2,
                        quantity=1
                    )

    print(f"--- Finished creating data for {schema_name} ---")

if __name__ == "__main__":
    import sys
    schema = sys.argv[1] if len(sys.argv) > 1 else 'pune'
    create_dummy_data(schema)
