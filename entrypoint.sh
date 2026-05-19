#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "Waiting for PostgreSQL..."
while ! pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER > /dev/null 2>&1; do
  sleep 1
done
echo "PostgreSQL is ready!"

if [ "$RUN_MIGRATIONS" = "1" ]; then
    echo "--- STARTING SAFE MIGRATION FIX ---"

    # fix_migrations.py uses Django's Python API directly.
    # It applies each migration in a savepoint and fakes any that fail
    # with "already exists" — no subprocess migrate_schemas calls at all.
    python fix_migrations.py
    echo "fix_migrations.py completed"

    # Bootstrap Public Tenant and Admin User
    echo "[*] Bootstrapping Public Tenant and Admin User..."
    python manage.py shell <<'PYEOF'
from tenants.models import City, Domain
from accounts.models import User
from django.db import transaction, connection
import os

try:
    with transaction.atomic():
        connection.set_schema_to_public()

        c, created = City.objects.get_or_create(
            schema_name='public',
            defaults={'name': 'Public', 'code': 'PUB', 'state': 'Main'}
        )
        if created:
            print("Created Public Tenant")

        Domain.objects.get_or_create(
            domain='localhost',
            tenant=c,
            defaults={'is_primary': True}
        )

        public_domain = os.environ.get('PUBLIC_DOMAIN')
        if public_domain and public_domain != 'localhost':
            Domain.objects.get_or_create(
                domain=public_domain,
                tenant=c,
                defaults={'is_primary': False}
            )
            print(f"Registered Domain: {public_domain}")

        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@dairy.com', 'admin')
            print("Created superuser: admin/admin")
        else:
            print("Admin user already exists — skipping")
except Exception as e:
    print(f"Bootstrapping failed (non-fatal): {e}")
PYEOF

    echo "[*] Setting up System Groups..."
    python manage.py setup_groups || echo "setup_groups failed — skipping"

    echo "[*] Collecting static files..."
    python manage.py collectstatic --noinput

    echo "--- MIGRATION FIX COMPLETE ---"
fi

# Execute the CMD
echo "Starting application..."
exec "$@"
