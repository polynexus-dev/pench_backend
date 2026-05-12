import os
import django
import random
from datetime import date, timedelta
from decimal import Decimal

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django_tenants.utils import schema_context
from django.contrib.gis.geos import Point

# Model Imports
from crm.models import Customer
from inventory.models import Product, BottleType, Warehouse, Stock, BottleTransaction, BottleTransactionType
from subscriptions.models import Subscription, SubscriptionItem, DeliveryFrequency
from orders.models import Order, OrderStatus

def generate_demo(schema_name):
    print(f"🚀 Generating Comprehensive Demo Data for: {schema_name}")
    
    try:
        with schema_context(schema_name):
            # 1. Create Warehouse
            warehouse, _ = Warehouse.objects.get_or_create(
                name=f"{schema_name.capitalize()} Main Hub",
                defaults={"address": f"Central Distribution Center, {schema_name.capitalize()}"}
            )
            print(f"✅ Warehouse Created: {warehouse.name}")

            # 2. Create Bottle Types
            glass_bottle, _ = BottleType.objects.get_or_create(
                name="1L Glass Bottle",
                defaults={"deposit_amount": 50.00, "volume_ml": 1000}
            )
            pet_bottle, _ = BottleType.objects.get_or_create(
                name="500ml Pet Bottle",
                defaults={"deposit_amount": 0.00, "volume_ml": 500}
            )

            # 3. Create Products
            products_data = [
                {"sku": "MILK-A2-1L", "name": "A2 Cow Milk (1L)", "price": 85.00, "bottle": glass_bottle, "returnable": True},
                {"sku": "MILK-STD-500", "name": "Standard Milk (500ml)", "price": 35.00, "bottle": pet_bottle, "returnable": False},
                {"sku": "PANEER-200G", "name": "Fresh Paneer (200g)", "price": 110.00, "bottle": None, "returnable": False},
                {"sku": "CURD-500G", "name": "Probiotic Curd (500g)", "price": 60.00, "bottle": None, "returnable": False},
            ]

            created_products = []
            for p_data in products_data:
                product, _ = Product.objects.get_or_create(
                    sku=p_data["sku"],
                    defaults={
                        "name": p_data["name"],
                        "unit_price": p_data["price"],
                        "bottle_type": p_data["bottle"],
                        "is_returnable": p_data["returnable"]
                    }
                )
                created_products.append(product)
                
                # 4. Initialize Stock for each product
                Stock.objects.get_or_create(
                    product=product,
                    warehouse=warehouse,
                    defaults={"quantity": random.randint(100, 500), "reorder_level": 20}
                )
            print(f"✅ {len(created_products)} Products & Stock Levels Created.")

            # 5. Create Customers & Subscriptions
            customer_names = ["Rahul Sharma", "Anjali Gupta", "Vikram Singh", "Sonia Verma"]
            for i, name in enumerate(customer_names):
                customer, created = Customer.objects.get_or_create(
                    phone=f"980000000{i}",
                    defaults={
                        "name": name,
                        "email": f"user{i}@{schema_name}.com",
                        "address": f"Street {i+1}, Block {random.randint(1,10)}, {schema_name.capitalize()}",
                        "location": Point(73.8 + (i * 0.01), 18.5 + (i * 0.01))
                    }
                )
                
                if created:
                    # Create a Daily Subscription
                    sub = Subscription.objects.create(
                        customer=customer,
                        frequency=DeliveryFrequency.DAILY,
                        start_date=date.today()
                    )
                    # Add Milk to Subscription
                    SubscriptionItem.objects.create(
                        subscription=sub,
                        product=created_products[0], # Milk A2
                        quantity=random.randint(1, 2)
                    )

                    # 6. Create a Sample "Pending" Order for today
                    Order.objects.create(
                        customer=customer,
                        delivery_date=date.today(),
                        status=OrderStatus.PENDING,
                        total_amount=created_products[0].unit_price,
                        delivery_address=customer.address
                    )

            print(f"✅ {len(customer_names)} Customers, Subscriptions, and Orders created.")
            print(f"✨ Demo Data Generation Complete for {schema_name}!")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    import sys
    # Usage: python generate_comprehensive_demo.py [schema_name]
    schema = sys.argv[1] if len(sys.argv) > 1 else 'nagpur'
    generate_demo(schema)
