#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "Waiting for PostgreSQL..."
while ! pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER > /dev/null 2>&1; do
  sleep 1
done
echo "PostgreSQL is ready!"

if [ "$RUN_MIGRATIONS" = "1" ]; then
    # 1. Create migrations (just in case they are missing)
    python manage.py makemigrations finance --noinput

    # 2. Run shared migrations
    echo "Running shared migrations..."
    python manage.py migrate_schemas --shared --noinput

    # 3. Setup Public Tenant and Admin User via a temporary Python script
    echo "Bootstrapping Public Tenant and Admin User..."
    python manage.py shell <<EOF
from tenants.models import City, Domain
from accounts.models import User
import os

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
else:
    print("Superuser 'admin' already exists.")
EOF

    # 4. Run tenant migrations (for existing cities)
    echo "Running tenant migrations..."
    python manage.py migrate_schemas --tenant --noinput
fi

# Execute the CMD
echo "Starting application..."
exec "$@"
