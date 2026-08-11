import sys
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context, get_tenant_model
from accounts.models import PasswordChangeLog

User = get_user_model()


class Command(BaseCommand):
    help = "Resets all rider/driver passwords to a specified password (default: Password@123) across all tenant schemas and records an activity log entry for each."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            type=str,
            default="Password@123",
            help="New password for all riders (default: Password@123)",
        )
        parser.add_argument(
            "--admin-username",
            type=str,
            default="admin",
            help="Username of admin performing the reset (default: admin)",
        )

    def handle(self, *args, **options):
        new_password = options["password"]
        admin_username = options["admin_username"]

        self.stdout.write(self.style.NOTICE("=== Starting Rider Password Reset ==="))
        self.stdout.write(f"Target Password: {new_password}")
        self.stdout.write(f"Admin Username: {admin_username}\n")

        # 1. Collect all tenant schemas
        schemas = set()
        try:
            TenantModel = get_tenant_model()
            for t in TenantModel.objects.all():
                schemas.add(t.schema_name)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not load tenant model: {e}"))

        schemas.add("public")

        # 2. Find admin user in public schema
        with schema_context("public"):
            admin_user = (
                User.objects.filter(username=admin_username).first()
                or User.objects.filter(is_superuser=True).first()
            )

        if not admin_user:
            self.stdout.write(
                self.style.WARNING(
                    f"Warning: Admin user '{admin_username}' not found. Logging with system fallback."
                )
            )

        # 3. Collect all rider user IDs across all tenant schemas and public schema
        rider_user_ids = set()

        # A. From public schema: all users with is_driver=True
        with schema_context("public"):
            for uid in User.objects.filter(is_driver=True).values_list("id", flat=True):
                rider_user_ids.add(uid)

        # B. From tenant schemas: all Driver profile model entries
        from routing.models import Driver

        for schema in sorted(schemas):
            if schema == "public":
                continue
            try:
                with schema_context(schema):
                    driver_ids = list(Driver.objects.values_list("user_id", flat=True))
                    self.stdout.write(f"Schema '{schema}': found {len(driver_ids)} Driver profile(s).")
                    for uid in driver_ids:
                        if uid:
                            rider_user_ids.add(uid)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Error checking schema '{schema}': {e}"))

        self.stdout.write(
            self.style.HTTP_INFO(
                f"\nFound {len(rider_user_ids)} total unique rider user(s) across all schemas."
            )
        )

        # 4. Reset password & create PasswordChangeLog in public schema
        total_reset = 0
        with schema_context("public"):
            for uid in sorted(rider_user_ids):
                rider = User.objects.filter(id=uid).first()
                if not rider:
                    continue

                rider.set_password(new_password)
                rider.save()

                PasswordChangeLog.objects.create(
                    user=rider,
                    changed_by=admin_user,
                    source="admin_batch_reset",
                    ip_address="127.0.0.1",
                )

                rider_name = rider.get_full_name() or rider.username
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [+] Reset rider #{rider.id} ({rider_name} | phone: {rider.phone}) -> Password set to {new_password}"
                    )
                )
                total_reset += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== SUCCESS: Reset passwords for {total_reset} rider(s). All activity log entries created. ==="
            )
        )
