import re
from django.core.management.base import BaseCommand, CommandError
from tenants.models import City, Domain


class Command(BaseCommand):
    help = "Updates tenant domains for a new VM IP or hostname."

    def add_arguments(self, parser):
        parser.add_argument(
            "new_target", type=str, help="The new VM IP address or hostname."
        )
        parser.add_argument(
            "--clean-old",
            type=str,
            help="An old IP address or hostname to clean up explicitly.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making database changes.",
        )
        parser.add_argument(
            "--no-cleanup",
            action="store_true",
            help="Skip the automatic cleanup of old IP/nip.io domains.",
        )

    def handle(self, *args, **options):
        new_target = options["new_target"].strip()
        clean_old = options["clean_old"]
        dry_run = options["dry_run"]
        no_cleanup = options["no_cleanup"]

        if not new_target:
            raise CommandError("A non-empty IP address or hostname must be specified.")

        # Match IPv4 pattern
        IP_REGEX = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
        is_ip = bool(IP_REGEX.match(new_target))

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Starting domain updates for target: {new_target} ({'IP Address' if is_ip else 'Hostname'})"
            )
        )
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "=== DRY RUN MODE: No database changes will be saved ==="
                )
            )

        # Define protected domains that should never be deleted automatically
        def is_protected(domain_name):
            d = domain_name.lower()
            if d == "localhost" or d.endswith(".localhost"):
                return True
            if d == "pench.api.polynexus.in" or d.endswith(".pench.api.polynexus.in"):
                return True
            return False

        # --- 1. Identify domains to create or update ---
        try:
            public_tenant = City.objects.get(schema_name="public")
        except City.DoesNotExist:
            raise CommandError(
                "Public tenant (schema_name='public') does not exist in the database."
            )

        other_tenants = City.objects.exclude(schema_name="public")

        domains_to_create_or_update = []  # list of tuples: (domain_name, tenant_obj)

        if is_ip:
            domains_to_create_or_update.append((new_target, public_tenant))
            domains_to_create_or_update.append((f"{new_target}.nip.io", public_tenant))
            for tenant in other_tenants:
                domains_to_create_or_update.append(
                    (f"{tenant.schema_name}.{new_target}.nip.io", tenant)
                )
        else:
            domains_to_create_or_update.append((new_target, public_tenant))
            for tenant in other_tenants:
                domains_to_create_or_update.append(
                    (f"{tenant.schema_name}.{new_target}", tenant)
                )

        # --- 2. Clean up old domains ---
        domains_to_delete = []
        if not no_cleanup:
            self.stdout.write(
                self.style.MIGRATE_LABEL("\nScanning for stale domains to clean up...")
            )
            for domain_obj in Domain.objects.all():
                d_name = domain_obj.domain.lower()
                if is_protected(d_name):
                    continue

                should_delete = False

                if IP_REGEX.match(d_name):
                    should_delete = True
                elif d_name.endswith(".nip.io"):
                    should_delete = True
                elif clean_old:
                    co = clean_old.strip().lower()
                    if d_name == co or d_name.endswith(f".{co}"):
                        should_delete = True

                if should_delete:
                    domains_to_delete.append(domain_obj)

            # Prevent deleting a domain we are about to register/update
            new_domain_names = {d[0].lower() for d in domains_to_create_or_update}
            domains_to_delete = [
                d for d in domains_to_delete if d.domain.lower() not in new_domain_names
            ]

            if domains_to_delete:
                for d in domains_to_delete:
                    if dry_run:
                        self.stdout.write(
                            self.style.NOTICE(
                                f"  [DRY-RUN] Would delete stale domain '{d.domain}' (mapped to tenant '{d.tenant.schema_name}')"
                            )
                        )
                    else:
                        d.delete()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  [DELETED] Stale domain '{d.domain}' (mapped to tenant '{d.tenant.schema_name}')"
                            )
                        )
            else:
                self.stdout.write("  No stale domains found to delete.")

        # --- 3. Register or Update new domains ---
        self.stdout.write(
            self.style.MIGRATE_LABEL("\nRegistering/updating active domains...")
        )
        for domain_name, tenant in domains_to_create_or_update:
            domain_name_lower = domain_name.lower()
            # Look up case-insensitively
            domain_obj = Domain.objects.filter(domain__iexact=domain_name_lower).first()

            if domain_obj:
                if domain_obj.tenant == tenant:
                    self.stdout.write(
                        f"  [EXISTS] Domain '{domain_name}' already mapped to tenant '{tenant.schema_name}'"
                    )
                else:
                    if dry_run:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  [DRY-RUN] Would update domain '{domain_name}' mapping from '{domain_obj.tenant.schema_name}' to '{tenant.schema_name}'"
                            )
                        )
                    else:
                        old_tenant_name = domain_obj.tenant.schema_name
                        domain_obj.tenant = tenant
                        domain_obj.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  [UPDATED] Domain '{domain_name}' moved from '{old_tenant_name}' to tenant '{tenant.schema_name}'"
                            )
                        )
            else:
                if dry_run:
                    self.stdout.write(
                        self.style.NOTICE(
                            f"  [DRY-RUN] Would create domain '{domain_name}' mapped to tenant '{tenant.schema_name}'"
                        )
                    )
                else:
                    Domain.objects.create(
                        domain=domain_name, tenant=tenant, is_primary=False
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  [CREATED] Domain '{domain_name}' mapped to tenant '{tenant.schema_name}'"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS("\nAll operations completed successfully!")
        )
