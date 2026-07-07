#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

READY_FILE="/app/media/.migrations_complete"

echo "Waiting for PostgreSQL..."
while ! pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER > /dev/null 2>&1; do
  sleep 1
done
echo "PostgreSQL is ready!"

if [ "$RUN_MIGRATIONS" = "1" ]; then
    echo "--- STARTING SAFE MIGRATION FIX ---"

    # Remove any stale ready-file from a previous run
    rm -f "$READY_FILE"

    # Automatically create the database if it doesn't exist
    python create_database.py

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

        # Auto-register all public/base domains
        base_domains = ['localhost', 'pench.api.polynexus.in', 'pench.dev.api.polynexus.in']
        for dom in base_domains:
            Domain.objects.get_or_create(
                domain=dom,
                tenant=c,
                defaults={'is_primary': (dom == 'localhost')}
            )
            print(f"Ensured domain mapping: {dom} -> public")

        # Auto-register tenant subdomains for other schemas
        other_cities = City.objects.exclude(schema_name='public')
        for city in other_cities:
            for base_dom in ['pench.api.polynexus.in', 'pench.dev.api.polynexus.in']:
                subdomain = f"{city.schema_name}.{base_dom}"
                Domain.objects.get_or_create(
                    domain=subdomain,
                    tenant=city,
                    defaults={'is_primary': False}
                )
                print(f"Ensured subdomain mapping: {subdomain} -> {city.schema_name}")

        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@dairy.com', 'admin')
            print("Created superuser: admin/admin")
        else:
            print("Admin user already exists — skipping")
except Exception as e:
    print(f"Bootstrapping failed (non-fatal): {e}")
PYEOF

    if [ -n "$PUBLIC_DOMAIN" ]; then
        echo "[*] Dynamically updating all tenant domains for PUBLIC_DOMAIN: $PUBLIC_DOMAIN"
        python manage.py update_domains "$PUBLIC_DOMAIN"
    fi

    echo "[*] Setting up System Groups..."
    python manage.py setup_groups || echo "setup_groups failed — skipping"

    echo "[*] Collecting static files..."
    python manage.py collectstatic --noinput

    echo "--- MIGRATION FIX COMPLETE ---"

    # Write the ready-file so beat/worker containers know migrations are done
    touch "$READY_FILE"
    echo "[*] Ready file written: $READY_FILE"

elif [ "$WAIT_FOR_READY" = "1" ]; then
    echo "Waiting for web migrations to complete..."
    WAIT_SECONDS=0
    while [ ! -f "$READY_FILE" ]; do
        sleep 2
        WAIT_SECONDS=$((WAIT_SECONDS + 2))
        if [ $WAIT_SECONDS -ge 180 ]; then
            echo "ERROR: Timed out waiting for migrations after 180s. Exiting."
            exit 1
        fi
        echo "  Still waiting... (${WAIT_SECONDS}s)"
    done
    echo "Migrations complete. Starting service..."
fi

# Execute the CMD
echo "Starting application..."
exec "$@"
