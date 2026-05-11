import os
import django
import uuid

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from crm.models import Customer
from django_tenants.utils import schema_context
from django.db import models

def fix_duplicates():
    print("[*] Switching to schema: pune")
    with schema_context('pune'):
        duplicates = Customer.objects.values('qr_code_id').annotate(
            count=models.Count('id')
        ).filter(count__gt=1)
        
        print(f"[*] Found {len(duplicates)} duplicate groups.")
        
        for dup in duplicates:
            qr_id = dup['qr_code_id']
            print(f"[*] Checking QR ID: '{qr_id}'")
            
            customers = Customer.objects.filter(qr_code_id=qr_id).order_by('id')
            print(f"[*] Found {customers.count()} customers for this ID.")
            
            if customers.count() > 1:
                # Keep the first one, update the rest
                for c in list(customers)[1:]:
                    new_uuid = str(uuid.uuid4())
                    print(f"    [>] Updating Customer ID {c.id}: {qr_id} -> {new_uuid}")
                    c.qr_code_id = new_uuid
                    c.save()

if __name__ == "__main__":
    fix_duplicates()
    print("[+] Done!")
