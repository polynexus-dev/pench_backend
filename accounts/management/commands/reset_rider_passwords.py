import sys
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context, get_tenant_model
from accounts.models import PasswordChangeLog

User = get_user_model()


class Command(BaseCommand):
    help = "Resets all rider/driver passwords to a specified password (default: Password@123) across all schemas and records an activity log entry for each."

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

        self.stdout.write(self.style.NOTICE(f"=== Starting Rider Password Reset ==="))
        self.stdout.write(f"Target Password: {new_password}")
        self.stdout.write(f"Admin Username: {admin_username}\n")

        # Collect schemas
        schemas = set()
        try:
            TenantModel = get_tenant_model()
            for t in TenantModel.objects.all():
                schemas.add(t.schema_name)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not load tenant model: {e}"))

        schemas.add("public")

        total_riders_reset = 0

        for schema in sorted(schemas):
            self.stdout.write(self.style.HTTP_INFO(f"\nProcessing Schema: '{schema}'..."))
            with schema_context(schema):
                # Find admin user for logging attribute
                admin_user = (
                    User.objects.filter(username=admin_username).first()
                    or User.objects.filter(is_superuser=True).first()
                )

                # Find all rider users
                # A user is a rider if is_driver=True or has a driver_profile attached
                riders = User.objects.filter(is_driver=True)

                if hasattr(User, "driver_profile"):
                    profile_user_ids = User.objects.filter(
                        driver_profile__isnull=False
                    ).values_list("id", flat=True)
                    riders = (riders | User.objects.filter(id__in=profile_user_ids)).distinct()

                count = 0
                for rider in riders:
                    rider.set_password(new_password)
                    rider.save()

                    # Record in PasswordChangeLog so it appears in the rider's Activity Log
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
                    count += 1
                    total_riders_reset += 1

                if count == 0:
                    self.stdout.write("  No riders found in this schema.")
                else:
                    self.stdout.write(f"  Reset {count} rider(s) in schema '{schema}'.")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== SUCCESS: Reset passwords for {total_riders_reset} total rider(s) across all schemas. ==="
            )
        )
