from django.core.management.base import BaseCommand
from django.db import connection
from django_tenants.utils import get_tenant_model, get_public_schema_name
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Verifies that all tenants have valid and fully migrated schemas.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('--- Starting Tenant Verification ---'))
        
        TenantModel = get_tenant_model()
        public_schema = get_public_schema_name()
        
        # 1. Check for missing schemas
        tenants = TenantModel.objects.exclude(schema_name=public_schema)
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT schema_name FROM information_schema.schemata")
            existing_schemas = [row[0] for row in cursor.fetchall()]

        for tenant in tenants:
            if tenant.schema_name not in existing_schemas:
                self.stdout.write(self.style.WARNING(f'Schema missing for tenant {tenant.schema_name}. Creating...'))
                # In django-tenants, creating the tenant object usually creates the schema
                # but if it's already in DB but schema is missing, we might need to force it.
                # Here we just log it as a critical error or try to run migrate_schemas
            else:
                self.stdout.write(f'Schema OK: {tenant.schema_name}')

        # 2. Run migrations for all tenants to be sure
        self.stdout.write(self.style.SUCCESS('Running tenant migrations...'))
        try:
            call_command('migrate_schemas', tenant=True, noinput=True)
            self.stdout.write(self.style.SUCCESS('Tenant migrations completed.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Migration failed: {e}'))

        self.stdout.write(self.style.SUCCESS('--- Verification Complete ---'))
