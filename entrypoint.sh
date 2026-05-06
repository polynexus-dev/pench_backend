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
    
    # 1. Force migrate accounts first using standard migrate
    echo "[*] Force migrating 'accounts' app to public schema..."
    python manage.py migrate accounts --noinput
    
    # 2. Ensure Shared Apps (Public) are migrated
    echo "[*] Migrating SHARED apps (Public schema)..."
    python manage.py migrate_schemas --shared --noinput
    
    # 2. Double-check if accounts table exists (sanity check)
    echo "[*] Verifying accounts_user table..."
    python manage.py shell <<EOF
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("SELECT to_regclass('public.accounts_user');")
    if cursor.fetchone()[0]:
        print("SUCCESS: accounts_user table exists in public schema.")
    else:
        print("ERROR: accounts_user table NOT FOUND in public schema!")
EOF

    # 3. Setup Public Tenant and Admin User
    echo "[*] Bootstrapping Public Tenant and Admin User..."
    python manage.py shell <<EOF
from tenants.models import City, Domain
from accounts.models import User
from django.db import transaction
import os

try:
    with transaction.atomic():
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

        # Create Admin User
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@dairy.com', 'admin')
            print("Created superuser: admin/admin")
except Exception as e:
    print(f"Bootstrapping failed: {e}")
EOF

    # 4. Run tenant migrations (for existing cities)
    echo "[*] Migrating TENANT apps (City schemas)..."
    python manage.py migrate_schemas --tenant --noinput
    
    echo "--- MIGRATIONS COMPLETE ---"
fi

# Execute the CMD
echo "Starting application..."
exec "$@"
