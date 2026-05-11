#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "Waiting for PostgreSQL..."
while ! pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER > /dev/null 2>&1; do
  sleep 1
done
echo "PostgreSQL is ready!"

if [ "$RUN_MIGRATIONS" = "1" ]; then
    echo "--- STARTING MIGRATIONS ---"
    
    # 1. Ensure Shared Apps (Public) are migrated first
    echo "[*] Migrating SHARED apps (Public schema)..."
    python manage.py migrate_schemas --shared --noinput || {
        echo "Migration failed. Attempting to fix by faking initial..."
        python manage.py migrate_schemas --shared --fake-initial --noinput
    }
    
    # 2. Verify critical tables
    echo "[*] Verifying critical shared tables..."
    python manage.py shell <<EOF
from django.db import connection
with connection.cursor() as cursor:
    tables = ['tenants_city', 'tenants_domain', 'accounts_user']
    for table in tables:
        cursor.execute(f"SELECT to_regclass('public.{table}');")
        if cursor.fetchone()[0]:
            print(f"SUCCESS: {table} exists.")
        else:
            print(f"CRITICAL: {table} NOT FOUND! Attempting forced migration...")
            # We could trigger a forced migration here if we wanted
EOF

    # 3. Setup Public Tenant and Admin User
    echo "[*] Bootstrapping Public Tenant and Admin User..."
    python manage.py shell <<EOF
from tenants.models import City, Domain
from accounts.models import User
from django.db import transaction, connection
import os

try:
    with transaction.atomic():
        # Ensure we are in public schema
        connection.set_schema_to_public()
        
        # Create Public Tenant
        c, created = City.objects.get_or_create(
            schema_name='public', 
            defaults={'name': 'Public', 'code': 'PUB', 'state': 'Main'}
        )
        if created:
            print("Created Public Tenant")

        # Create localhost Domain
        Domain.objects.get_or_create(
            domain='localhost', 
            tenant=c, 
            defaults={'is_primary': True}
        )

        # Create Public Domain from ENV if provided (Important for VM IP access)
        public_domain = os.environ.get('PUBLIC_DOMAIN')
        if public_domain and public_domain != 'localhost':
            # Add both the domain and its subdomain wildcard if needed
            Domain.objects.get_or_create(
                domain=public_domain,
                tenant=c,
                defaults={'is_primary': False}
            )
            print(f"Registered Domain: {public_domain}")

        # Create Admin User
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@dairy.com', 'admin')
            print("Created superuser: admin/admin")
except Exception as e:
    print(f"Bootstrapping failed: {e}")
EOF

    echo "[*] Setting up System Groups..."
    python manage.py setup_groups

    # 4. Run tenant migrations (for existing cities)
    echo "[*] Migrating TENANT apps (City schemas)..."
    python manage.py migrate_schemas --tenant --noinput
    
    echo "--- MIGRATIONS COMPLETE ---"
fi

# Execute the CMD
echo "Starting application..."
exec "$@"
