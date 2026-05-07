from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context
from tenants.models import City
from routing.models import Driver
from django.db import connection

class Command(BaseCommand):
    help = 'Debug driver placement across schemas'

    def handle(self, *args, **options):
        # 1. Check Public Schema
        with schema_context('public'):
            # In your config, routing is NOT in SHARED_APPS, so this table shouldn't exist here.
            # But let's check for "shadow" data.
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'routing_driver'")
                exists = cursor.fetchone()[0]
                if exists:
                    count = Driver.objects.count()
                    self.stdout.write(self.style.WARNING(f"Found {count} drivers in PUBLIC schema (This is usually WRONG)."))
                else:
                    self.stdout.write(self.style.SUCCESS("Public schema is clean of driver data."))

        # 2. Check each City
        cities = City.objects.exclude(schema_name='public')
        for city in cities:
            with schema_context(city.schema_name):
                drivers = Driver.objects.all()
                self.stdout.write(self.style.SUCCESS(f"--- City: {city.name} ({city.schema_name}) ---"))
                if not drivers.exists():
                    self.stdout.write("  No drivers found.")
                for driver in drivers:
                    user_info = f"{driver.user.username} (ID: {driver.user_id})" if driver.user else "NULL USER"
                    self.stdout.write(f"  - Driver ID: {driver.id} | User: {user_info} | Plate: {driver.vehicle_plate}")
