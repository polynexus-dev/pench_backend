import re
import sys
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django_tenants.utils import schema_context, get_tenant_model

User = get_user_model()

TITLES = {"mr", "mrs", "ms", "dr", "prof", "shri", "smt"}

DEFAULT_PLACEHOLDERS = {
    # Literal placeholder indicators
    "placeholder",
    "unknown",
    "na",
    "none",
    "null",
    "nil",
    "notavailable",
    "not_available",
    "noname",
    "no_name",
    "unassigned",
    "undefined",
    "empty",
    "blank",
    # Generic role/type words often used when last name is missing
    "user",
    "customer",
    "cust",
    "driver",
    "rider",
    "admin",
    "superadmin",
    "staff",
    "manager",
    "employee",
    "member",
    "delivery",
    # Test/dummy words
    "test",
    "testing",
    "dummy",
    "demo",
    "sample",
    "temp",
    "temporary",
    "fake",
    "doe",
    # Generic naming words
    "surname",
    "lastname",
    "firstname",
    "name",
}


def clean_alpha_string(text: str) -> str:
    """Removes all digits and non-alphabetic characters, preserving spaces."""
    if not text:
        return ""
    # Strip any numbers and non-alphabetic characters (keep letters and spaces)
    return re.sub(r"[^a-zA-Z\s]", "", str(text)).strip()


def filter_tokens(tokens: list[str], placeholders: set[str]) -> list[str]:
    """Filters out titles and placeholder words from name tokens."""
    filtered = []
    for t in tokens:
        tl = t.lower()
        if tl in TITLES:
            continue
        if tl in placeholders:
            continue
        filtered.append(tl)
    return filtered


def parse_names(
    first_name: str,
    last_name: str,
    placeholders: set[str] = DEFAULT_PLACEHOLDERS,
):
    """
    Parses first_name and last_name:
    - Strips all numbers/digits (strictly no numbers)
    - Strips salutations/titles
    - Filters out placeholders (e.g. 'placeholder', 'user', 'customer', 'na', etc.)
    - Returns (clean_first, clean_last) where each is either a lowercase alpha string or None
    """
    f_cleaned = clean_alpha_string(first_name)
    l_cleaned = clean_alpha_string(last_name)

    f_words = filter_tokens(f_cleaned.split(), placeholders)
    l_words = filter_tokens(l_cleaned.split(), placeholders)

    all_words = f_words + l_words
    if not all_words:
        return None, None
    if len(all_words) == 1:
        return all_words[0], None

    return all_words[0], "_".join(all_words[1:])


def build_pench_username(
    first_name: str,
    last_name: str,
    placeholders: set[str] = DEFAULT_PLACEHOLDERS,
) -> str | None:
    """
    Builds username following:
    - Prefix: pench_
    - firstname_lastname if both available and non-placeholder
    - firstname if only first available (last name missing or placeholder)
    - lastname if only last available (first name missing or placeholder)
    - None if neither available (skip)
    - STRICTLY NO NUMBERS
    """
    first, last = parse_names(first_name, last_name, placeholders)
    if not first and not last:
        return None

    parts = []
    if first:
        parts.append(first)
    if last:
        parts.append(last)

    return f"pench_{'_'.join(parts)}"


def get_alpha_suffix(index: int) -> str:
    """
    Generates alphabetic suffix for collisions without any numbers:
    0 -> 'a', 1 -> 'b', ..., 25 -> 'z', 26 -> 'aa', etc.
    """
    chars = []
    while True:
        chars.append(chr(ord("a") + (index % 26)))
        index = index // 26 - 1
        if index < 0:
            break
    return "".join(reversed(chars))


class Command(BaseCommand):
    help = (
        "Updates usernames on VM to 'pench_firstname_lastname' format. "
        "Adds first and last name if available else skips. "
        "Automatically skips placeholder last names (e.g. 'placeholder', 'user', 'na', 'none'). "
        "Strictly no numbers."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the changes to the database. If not set, runs in dry-run mode.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate changes without modifying the database (default behavior if --apply is omitted).",
        )
        parser.add_argument(
            "--include-superusers",
            action="store_true",
            help="Include superusers and staff members (excluded by default to prevent admin lockout).",
        )
        parser.add_argument(
            "--on-collision",
            choices=["skip", "alpha"],
            default="skip",
            help="How to handle collisions without numbers. 'skip' (default) skips duplicates. 'alpha' appends _a, _b, etc.",
        )
        parser.add_argument(
            "--role",
            choices=["all", "customers", "drivers", "erp"],
            default="all",
            help="Filter users by role (default: all).",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            help="Update a specific user by primary key ID.",
        )
        parser.add_argument(
            "--add-placeholders",
            type=str,
            default="",
            help="Comma-separated additional placeholder words to ignore (e.g. 'testname,dummyname').",
        )
        parser.add_argument(
            "--no-placeholder-filter",
            action="store_true",
            help="Disable filtering out placeholder last names.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"] and not options["dry_run"]
        include_superusers = options["include_superusers"]
        on_collision = options["on_collision"]
        role_filter = options["role"]
        target_user_id = options.get("user_id")

        # Configure placeholders
        if options["no_placeholder_filter"]:
            active_placeholders = set()
        else:
            active_placeholders = set(DEFAULT_PLACEHOLDERS)
            if options["add_placeholders"]:
                custom_words = [
                    w.strip().lower()
                    for w in options["add_placeholders"].split(",")
                    if w.strip()
                ]
                active_placeholders.update(custom_words)

        mode_str = "APPLY (WRITING TO DATABASE)" if apply_changes else "DRY-RUN (NO CHANGES SAVED)"
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== USERNAME UPDATE SCRIPT ==="))
        self.stdout.write(self.style.WARNING(f"Mode: {mode_str}"))
        self.stdout.write(f"Collision strategy: {on_collision} (strictly no numbers)")
        self.stdout.write(f"Role filter: {role_filter}")
        self.stdout.write(f"Include superusers: {include_superusers}")
        self.stdout.write(f"Placeholder filtering: {'Active (' + str(len(active_placeholders)) + ' words)' if active_placeholders else 'Disabled'}\n")

        # Fetch tenant schemas to find names if user.first_name and user.last_name are empty
        schemas = []
        try:
            TenantModel = get_tenant_model()
            for t in TenantModel.objects.all():
                if t.schema_name != "public":
                    schemas.append(t.schema_name)
        except Exception:
            pass

        # Build user query
        users_qs = User.objects.all().order_by("id")

        if target_user_id:
            users_qs = users_qs.filter(id=target_user_id)

        if not include_superusers:
            users_qs = users_qs.filter(is_superuser=False, is_staff=False)

        if role_filter == "customers":
            users_qs = users_qs.filter(is_customer=True)
        elif role_filter == "drivers":
            users_qs = users_qs.filter(is_driver=True)
        elif role_filter == "erp":
            users_qs = users_qs.filter(is_erp_user=True)

        users = list(users_qs)
        self.stdout.write(f"Found {len(users)} users matching criteria.\n")

        # Map of existing usernames in database (username -> user_id)
        existing_usernames = {
            u.username.lower(): u.id
            for u in User.objects.all().only("id", "username")
        }

        # Keep track of newly assigned usernames in this run
        planned_usernames = {}  # username -> user_id

        stats = {
            "total": len(users),
            "updated": 0,
            "already_correct": 0,
            "skipped_no_name": 0,
            "skipped_collision": 0,
            "resolved_collision_alpha": 0,
        }

        changes_to_save = []

        for user in users:
            first_name = user.first_name or ""
            last_name = user.last_name or ""

            # If user has no names in User model, try to find customer profile in tenant schemas
            if not first_name.strip() and not last_name.strip():
                first_name, last_name = self.find_name_from_profiles(user, schemas)

            # Generate target username with placeholder filtering
            new_username = build_pench_username(
                first_name, last_name, placeholders=active_placeholders
            )

            if not new_username:
                stats["skipped_no_name"] += 1
                self.stdout.write(
                    self.style.NOTICE(
                        f"[-] User #{user.id} ({user.username}): Skipped — No valid name found (empty or placeholder)."
                    )
                )
                continue

            # Check if current username already matches target
            if user.username.lower() == new_username.lower():
                stats["already_correct"] += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[=] User #{user.id} ({user.username}): Already in correct format."
                    )
                )
                continue

            # Check for collisions
            candidate_username = new_username
            collision = False

            # Check if candidate_username is already taken by ANOTHER user in DB or in this batch
            is_taken_in_db = (
                candidate_username in existing_usernames
                and existing_usernames[candidate_username] != user.id
            )
            is_taken_in_batch = (
                candidate_username in planned_usernames
                and planned_usernames[candidate_username] != user.id
            )

            if is_taken_in_db or is_taken_in_batch:
                collision = True

            if collision:
                if on_collision == "alpha":
                    # Append alphabetic suffix without any numbers: _a, _b, ...
                    suffix_idx = 0
                    while True:
                        alpha_suffix = get_alpha_suffix(suffix_idx)
                        alt_username = f"{new_username}_{alpha_suffix}"
                        if (
                            alt_username not in existing_usernames
                            and alt_username not in planned_usernames
                        ):
                            candidate_username = alt_username
                            stats["resolved_collision_alpha"] += 1
                            break
                        suffix_idx += 1
                else:
                    # Skip collision strictly without adding numbers
                    stats["skipped_collision"] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"[!] User #{user.id} ({user.username}): Collision on '{candidate_username}' — Skipped (no numbers added)."
                        )
                    )
                    continue

            # Plan change
            planned_usernames[candidate_username] = user.id
            changes_to_save.append((user, candidate_username, first_name, last_name))
            stats["updated"] += 1

            self.stdout.write(
                self.style.MIGRATE_LABEL(
                    f"[+] User #{user.id} ({user.username}) -> '{candidate_username}' [Raw Name: {first_name or '-'} {last_name or '-'}]"
                )
            )

        # Apply changes if confirmed
        if apply_changes and changes_to_save:
            self.stdout.write(self.style.NOTICE("\nApplying changes within transaction..."))
            with transaction.atomic():
                for user, target_username, f_name, l_name in changes_to_save:
                    user.username = target_username
                    # If first_name / last_name were blank or placeholder on user, populate cleaned names if available
                    cleaned_f, cleaned_l = parse_names(
                        f_name, l_name, placeholders=active_placeholders
                    )
                    if not user.first_name and cleaned_f:
                        user.first_name = cleaned_f.capitalize()
                    if cleaned_l:
                        user.last_name = " ".join(
                            part.capitalize() for part in cleaned_l.split("_")
                        )
                    elif (
                        user.last_name
                        and user.last_name.lower().strip() in active_placeholders
                    ):
                        # Clear placeholder last name from DB as well
                        user.last_name = ""
                    user.save(update_fields=["username", "first_name", "last_name"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully updated {len(changes_to_save)} users in database!"
                )
            )
        elif not apply_changes and changes_to_save:
            self.stdout.write(
                self.style.WARNING(
                    f"\n[DRY RUN COMPLETE] {len(changes_to_save)} usernames will be updated. Run with --apply to commit."
                )
            )

        # Summary
        self.stdout.write("\n" + "=" * 40)
        self.stdout.write(self.style.MIGRATE_HEADING("SUMMARY:"))
        self.stdout.write(f"Total Users Checked:       {stats['total']}")
        self.stdout.write(f"Usernames To Update/Updated:{stats['updated']}")
        self.stdout.write(f"Already Correct Format:     {stats['already_correct']}")
        self.stdout.write(f"Skipped (No Valid Name):    {stats['skipped_no_name']}")
        self.stdout.write(f"Skipped (Collision):        {stats['skipped_collision']}")
        if on_collision == "alpha":
            self.stdout.write(f"Collision Alpha-Resolved:   {stats['resolved_collision_alpha']}")
        self.stdout.write("=" * 40 + "\n")

    def find_name_from_profiles(self, user, schemas):
        """Attempts to find first and last name from linked Customer or Employee records."""
        # 1. Check HR Employee profile
        try:
            if hasattr(user, "employee_profile") and user.employee_profile:
                emp = user.employee_profile
                pass
        except Exception:
            pass

        # 2. Check Customer profile across tenant schemas
        for schema in schemas:
            try:
                with schema_context(schema):
                    from crm.models import Customer
                    cust = Customer.objects.filter(user=user).first()
                    if cust and cust.name:
                        return cust.name, ""
            except Exception:
                continue

        return "", ""
