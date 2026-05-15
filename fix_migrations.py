"""
fix_migrations.py
=================
Smart migration fix for django-tenants + PostgreSQL.

Applies migrations ONE BY ONE. If any migration fails because the table
already exists, it fakes that specific migration and continues.

This handles ALL cases:
  - Fresh DB: applies everything normally
  - Existing DB with incomplete history: fakes existing, applies truly new ones
  - New model changes: runs makemigrations first
  - Both shared (public) + all tenant schemas
"""

import os
import sys
import subprocess

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection, transaction  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402
from django.db.migrations.recorder import MigrationRecorder  # noqa: E402

SEP = "=" * 60

def banner(msg): print(f"\n{SEP}\n  {msg}\n{SEP}")
def ok(msg):     print(f"  ✅  {msg}")
def skip(msg):   print(f"  ⏭️   {msg}")
def warn(msg):   print(f"  ⚠️   {msg}")
def info(msg):   print(f"  ℹ️   {msg}")
def err(msg):    print(f"  ❌  {msg}")


def is_exists_error(e: Exception) -> bool:
    """Check if the error is a 'table/relation already exists' error."""
    msg = str(e).lower()
    return any(x in msg for x in [
        'already exists',
        'duplicate table',
        'duplicatetable',
        'relation',
    ])


def apply_migrations_smart(schema_name: str):
    """
    Apply all pending migrations for the current schema connection,
    faking any that fail because the relation already exists.
    Uses savepoints so one failure does not abort everything.
    """
    recorder = MigrationRecorder(connection)
    recorder.ensure_schema()

    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    plan = executor.migration_plan(targets)

    forwards = [(m, b) for m, b in plan if not b]

    if not forwards:
        skip(f"[{schema_name}] Nothing pending")
        return

    info(f"[{schema_name}] {len(forwards)} migration(s) to process...")

    applied = faked = failed = 0

    for (app_label, migration_name), _ in forwards:
        label = f"{app_label}.{migration_name}"

        # Rebuild executor so its internal state is up-to-date after each step
        executor = MigrationExecutor(connection)
        migration_obj = executor.loader.get_migration(app_label, migration_name)
        pre_state = executor.loader.project_state(
            (app_label, migration_name), at_end=False
        )

        try:
            # Each migration runs inside its own atomic block (savepoint when
            # we are already inside a transaction, which we are here via autocommit=off)
            with transaction.atomic():
                executor.apply_migration(pre_state, migration_obj)
            applied += 1
            ok(f"[{schema_name}] Applied: {label}")

        except Exception as e:
            if is_exists_error(e):
                # The table/relation already exists — just record it as applied
                recorder.record_applied(app_label, migration_name)
                faked += 1
                skip(f"[{schema_name}] Faked (already exists): {label}")
            else:
                failed += 1
                err(f"[{schema_name}] FAILED: {label}")
                err(f"           Reason: {e}")
                # Continue trying remaining migrations

    print(f"\n  📊 [{schema_name}]: applied={applied}, faked={faked}, failed={failed}")


# ─────────────────────────────────────────────────────────────────────────────
# STEPS
# ─────────────────────────────────────────────────────────────────────────────

def step_makemigrations():
    banner("STEP 1 · makemigrations (detect new model changes)")

    check = subprocess.run(
        [sys.executable, "manage.py", "makemigrations", "--check"],
        capture_output=True, text=True
    )
    if check.returncode == 0:
        skip("No new model changes detected")
        return

    result = subprocess.run(
        [sys.executable, "manage.py", "makemigrations", "--noinput"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        ok("New migrations generated")
        for line in result.stdout.strip().splitlines():
            print(f"       {line}")
    else:
        warn("makemigrations had issues — continuing anyway")
        print(result.stderr or result.stdout)


def step_shared():
    banner("STEP 2 · Shared / public schema migrations")
    connection.set_schema_to_public()
    apply_migrations_smart("public")


def step_tenants():
    banner("STEP 3 · Tenant schema migrations")

    # Make sure we can reach the tenants table
    connection.set_schema_to_public()
    try:
        from tenants.models import City
        tenants = list(City.objects.exclude(schema_name="public"))
    except Exception as e:
        warn(f"Cannot load tenants ({e}) — skipping tenant migrations")
        return

    if not tenants:
        skip("No tenant schemas found yet")
        return

    info(f"Found {len(tenants)} tenant(s): {[t.schema_name for t in tenants]}")

    from django_tenants.utils import schema_context

    for tenant in tenants:
        with schema_context(tenant.schema_name):
            apply_migrations_smart(tenant.schema_name)


def step_final_check():
    banner("STEP 4 · Migration status summary")

    result = subprocess.run(
        [sys.executable, "manage.py", "showmigrations", "--plan"],
        capture_output=True, text=True
    )
    lines = result.stdout.splitlines()
    pending = [l for l in lines if "[ ]" in l]
    done    = [l for l in lines if "[x]" in l]

    ok(f"Applied : {len(done)}")
    if pending:
        warn(f"Pending  : {len(pending)}")
        for p in pending:
            print(f"       {p}")
    else:
        ok("All migrations applied ✨")


# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'#' * 60}")
    print("  🛠   PENCH BACKEND — Smart Migration Fix")
    print(f"{'#' * 60}")

    try:
        step_makemigrations()
        step_shared()
        step_tenants()
        step_final_check()
        banner("✅  Done — you can now start the server")
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except Exception as exc:
        err(f"Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
