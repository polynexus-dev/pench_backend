import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def find_all_duplicates():
    cursor = connection.cursor()
    cursor.execute("SELECT schema_name FROM tenants_city")
    schemas = [r[0] for r in cursor.fetchall()]
    
    for s in schemas:
        print(f"Checking {s}...")
        try:
            cursor.execute(f'SET search_path TO "{s}"')
            cursor.execute('SELECT id, qr_code_id FROM crm_customer')
            rows = cursor.fetchall()
            
            seen = {}
            for row_id, qr_id in rows:
                if qr_id in seen:
                    print(f"  [!] DUPLICATE in {s}: {qr_id} (IDs: {seen[qr_id]}, {row_id})")
                else:
                    seen[qr_id] = row_id
        except Exception as e:
            print(f"  [Error] {e}")

if __name__ == "__main__":
    find_all_duplicates()
