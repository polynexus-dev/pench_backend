import os
import sys
import django

# Add current directory to python path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from django_tenants.utils import schema_context
from accounts.models import User
from crm.models import Customer

schema_name = "pench_nagpur"
with schema_context(schema_name):
    connection.set_schema(schema_name)
    
    customers = Customer.objects.all()
    print(f"Total customers: {len(customers)}")
    
    linked_count = 0
    unlinked_has_phone_in_user = 0
    unlinked_has_phone_not_in_user = 0
    unlinked_no_phone = 0
    
    for c in customers:
        if c.user:
            linked_count += 1
        else:
            if c.phone:
                phone = c.phone.strip()
                # Check if phone is in User table
                u = User.objects.filter(phone=phone).first()
                if not u and len(phone) >= 10:
                    u = User.objects.filter(phone__endswith=phone[-10:]).first()
                
                if u:
                    unlinked_has_phone_in_user += 1
                    # Check who is linked to that user
                    linked_c = Customer.objects.filter(user=u).first()
                    print(f"Unlinked Customer: '{c.name}' (phone={c.phone}) has matching User '{u.username}' already linked to '{linked_c.name if linked_c else 'None'}'")
                else:
                    unlinked_has_phone_not_in_user += 1
                    print(f"Unlinked Customer (not in User): '{c.name}' (phone={c.phone}, email={c.email})")
            else:
                unlinked_no_phone += 1
                print(f"Unlinked Customer (no phone): '{c.name}' (email={c.email})")
                
    print("\nSummary:")
    print(f"Linked: {linked_count}")
    print(f"Unlinked, phone matches existing User: {unlinked_has_phone_in_user}")
    print(f"Unlinked, phone does not match any User: {unlinked_has_phone_not_in_user}")
    print(f"Unlinked, no phone: {unlinked_no_phone}")
