import os
import django
import sys

sys.path.append(os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django_tenants.utils import schema_context
from crm.models import Customer
from orders.models import Order

def check():
    with schema_context('nagpur'):
        test_customers = [
            # test1
            'Diya Sharma', 'Priya Iyer', 'Siddharth Joshi',
            # test2
            'Aanya Patel', 'Aarav Sharma', 'Meera Nair', 'Rohan Verma',
            # test3
            'Dev Kumar', 'Ishaan Gupta', 'Kabir Singh'
        ]
        
        print("=== Checking orders for original test customers ===")
        for name in test_customers:
            cust = Customer.objects.filter(name=name).first()
            if not cust:
                print(f"Customer {name} not found.")
                continue
            
            orders = Order.objects.filter(customer=cust)
            print(f"Customer: {cust.name} (Zone: {cust.zone.name if cust.zone else 'None'})")
            print(f"  Orders count: {orders.count()}")
            for o in orders:
                print(f"    * Order ID: {o.id}, Date: {o.scheduled_delivery_date}, Status: {o.status}")

if __name__ == '__main__':
    check()
