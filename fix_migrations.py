"""
fix_migrations.py — Smart Migration Fix for django-tenants
===========================================================

Uses Django's Python API directly (NO subprocess calls to migrate_schemas).
Applies each migration individually inside a savepoint.
If a migration fails with "table already exists", it fakes ONLY that migration
and continues with the next one.

Works for ALL cases:
  ✅ Fresh DB                  → applies everything normally
  ✅ Existing DB + empty history → fakes existing tables, applies new ones
  ✅ Partial history            → only applies what's missing
  ✅ New model changes          → makemigrations + apply
  ✅ Shared (public) schema     → handled
  ✅ All tenant schemas         → handled via schema_context
"""

import os
import sys
import subprocess

# Reconfigure stdout/stderr to use UTF-8 encoding (especially on Windows to prevent UnicodeEncodeError when printing emojis)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402
from django.db.migrations.recorder import MigrationRecorder  # noqa: E402

S = "=" * 58

def banner(m): print(f"\n{S}\n  {m}\n{S}")
def ok(m):     print(f"  ✅  {m}")
def skip(m):   print(f"  ⏭️   {m}")
def warn(m):   print(f"  ⚠️   {m}")
def info(m):   print(f"  ℹ️   {m}")
def err(m):    print(f"  ❌  {m}")


def is_exists_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("already exists" in msg
            or "duplicate" in msg
            or "duplicatetable" in msg)


def apply_all_pending(schema_label: str):
    """
    Apply every pending migration for whatever schema the connection
    is currently set to. Fakes any that fail with 'already exists'.
    """
    # Ensure the django_migrations tracking table is present
    recorder = MigrationRecorder(connection)
    recorder.ensure_schema()

    # Fresh executor — reads the current applied set from the DB
    executor = MigrationExecutor(connection)
    leaf_nodes = executor.loader.graph.leaf_nodes()
    plan = executor.migration_plan(leaf_nodes)
    # plan is list of (Migration_object, is_backward) tuples
    forwards = [(m, b) for m, b in plan if not b]

    if not forwards:
        skip(f"[{schema_label}] Nothing to apply")
        return

    info(f"[{schema_label}] {len(forwards)} migration(s) pending...")

    applied = faked = failed = 0

    for migration, _ in forwards:
        app_label = migration.app_label
        mig_name  = migration.name
        label     = f"{app_label}.{mig_name}"

        # Rebuild executor each loop so its state graph reflects
        # any migrations we just applied / faked above.
        executor = MigrationExecutor(connection)
        try:
            pre_state = executor.loader.project_state(
                (app_label, mig_name), at_end=False
            )
        except Exception as e:
            warn(f"[{schema_label}] Cannot compute pre-state for {label}: {e}")
            failed += 1
            continue

        migration_obj = executor.loader.get_migration(app_label, mig_name)

        try:
            # apply_migration internally wraps in atomic() / savepoint.
            # If it raises, Django rolls back that savepoint automatically,
            # leaving the connection in a clean state for the next iteration.
            executor.apply_migration(pre_state, migration_obj)
            applied += 1
            ok(f"[{schema_label}] Applied  : {label}")

        except Exception as exc:
            if is_exists_error(exc):
                # Table/index already exists — record as applied without touching DB
                try:
                    recorder.record_applied(app_label, mig_name)
                    faked += 1
                    skip(f"[{schema_label}] Faked    : {label}  (table exists)")
                except Exception as rec_exc:
                    # Connection might be in aborted state — reset and retry
                    try:
                        connection.rollback()
                        recorder.record_applied(app_label, mig_name)
                        faked += 1
                        skip(f"[{schema_label}] Faked*   : {label}")
                    except Exception:
                        err(f"[{schema_label}] Could not fake {label}: {rec_exc}")
                        failed += 1
            else:
                failed += 1
                err(f"[{schema_label}] FAILED   : {label}")
                err(f"           Reason  : {exc}")
                # Try to reset connection for next migration
                try:
                    connection.rollback()
                except Exception:
                    pass

    print(f"  📊 [{schema_label}] done — applied={applied}  faked={faked}  failed={failed}")


# ─────────────────────────────────────────────────────────────

def step_makemigrations():
    banner("STEP 1 · makemigrations — detect new model changes")
    check = subprocess.run(
        [sys.executable, "manage.py", "makemigrations", "--check"],
        capture_output=True, text=True
    )
    if check.returncode == 0:
        skip("No new model changes")
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
        warn("makemigrations had issues (continuing):")
        print(result.stderr or result.stdout)


def step_shared():
    banner("STEP 2 · Shared (public) schema")
    connection.set_schema_to_public()
    cleanup_inconsistent_migrations("public")
    apply_all_pending("public")


def step_tenants():
    banner("STEP 3 · Tenant schemas")
    connection.set_schema_to_public()

    try:
        from tenants.models import City
        tenants = list(City.objects.exclude(schema_name="public"))
    except Exception as exc:
        warn(f"Cannot load tenants ({exc}) — skipping")
        return

    if not tenants:
        skip("No tenant schemas found yet")
        return

    info(f"Tenants: {[t.schema_name for t in tenants]}")

    try:
        from django_tenants.utils import schema_context
    except ImportError:
        err("django_tenants not installed — cannot process tenant schemas")
        return

    for tenant in tenants:
        with schema_context(tenant.schema_name):
            cleanup_inconsistent_migrations(tenant.schema_name)
            apply_all_pending(tenant.schema_name)


def step_summary():
    banner("STEP 4 · Summary")
    result = subprocess.run(
        [sys.executable, "manage.py", "showmigrations", "--plan"],
        capture_output=True, text=True
    )
    lines = result.stdout.splitlines()
    pending = [l for l in lines if "[ ]" in l]
    done    = [l for l in lines if "[x]" in l]
    ok(f"Applied : {len(done)}")
    if pending:
        warn(f"Pending : {len(pending)}")
        for p in pending:
            print(f"       {p}")
    else:
        ok("All migrations in sync ✨")

# ─────────────────────────────────────────────────────────────

def step_pre_migration_cleanup():
    banner("STEP 0 · Pre-migration database consistency check")
    connection.set_schema_to_public()
    
    # Check if django_migrations table exists
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'django_migrations'
            );
        """)
        migrations_exists = cursor.fetchone()[0]
        
        if not migrations_exists:
            info("django_migrations table does not exist yet. No cleanup needed.")
            return

        # Check if tenants_city table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'tenants_city'
            );
        """)
        tenants_city_exists = cursor.fetchone()[0]

        if not tenants_city_exists:
            # The base table tenants_city does not exist, but django_migrations does.
            # This indicates an inconsistent or partially reset database.
            # We must clear django_migrations to allow Django to apply everything from scratch.
            warn("tenants_city table does not exist, but django_migrations table is present.")
            warn("Clearing django_migrations to prevent InconsistentMigrationHistory errors.")
            cursor.execute("TRUNCATE public.django_migrations CASCADE;")
            ok("Successfully truncated django_migrations in public schema.")
        else:
            info("tenants_city table exists. Database has been initialized.")


def cleanup_inconsistent_migrations(schema_label: str):
    """
    Checks if there are applied migrations in the database that have unapplied dependencies.
    If found, deletes the applied records of those migrations from django_migrations,
    making the history consistent so Django can re-evaluate and apply/fake them.
    """
    # Ensure the django_migrations tracking table is present
    from django.db.migrations.recorder import MigrationRecorder
    recorder = MigrationRecorder(connection)
    recorder.ensure_schema()

    from django.db.migrations.loader import MigrationLoader
    loader = MigrationLoader(connection, ignore_no_migrations=True)
    applied = loader.applied_migrations  # set of (app_label, migration_name)
    node_map = loader.graph.node_map

    to_delete = set()
    for migration in applied:
        if migration in node_map:
            node = node_map[migration]
            for parent in node.parents:
                if parent.key not in applied:
                    warn(f"[{schema_label}] Migration {migration} is marked as applied, but its dependency {parent.key} is not applied.")
                    to_delete.add(migration)
                    break

    if to_delete:
        # We need to recursively add any children of these nodes, since if we unapply X,
        # any Y that depends on X must also be unapplied.
        descendants = set()
        queue = list(to_delete)
        while queue:
            node_key = queue.pop(0)
            if node_key not in descendants:
                descendants.add(node_key)
                if node_key in node_map:
                    for child in node_map[node_key].children:
                        if child.key in applied:
                            queue.append(child.key)

        info(f"[{schema_label}] Removing the following migration records from django_migrations to restore consistency: {descendants}")
        with connection.cursor() as cursor:
            for app_label, migration_name in descendants:
                cursor.execute(
                    "DELETE FROM django_migrations WHERE app = %s AND name = %s",
                    [app_label, migration_name]
                )
        ok(f"[{schema_label}] Inconsistent migration records deleted successfully.")

        # Verify that check_consistent_history now passes
        try:
            # Recreate loader to verify
            loader = MigrationLoader(connection, ignore_no_migrations=True)
            loader.check_consistent_history(connection)
            ok(f"[{schema_label}] Database migration history is now consistent!")
        except Exception as e:
            warn(f"[{schema_label}] History still inconsistent after cleanup: {e}")
    else:
        info(f"[{schema_label}] Database migration history is consistent.")


# ─────────────────────────────────────────────────────────────

def main():
    print(f"\n{'#' * 58}")
    print("  🛠   PENCH — Smart Migration Fix  (Python API mode)")
    print(f"{'#' * 58}")
    try:
        step_pre_migration_cleanup()
        cleanup_inconsistent_migrations("public")
        step_makemigrations()
        step_shared()
        step_tenants()
        step_summary()
        banner("✅  Migration fix complete — server can start")
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except Exception as exc:
        err(f"Unexpected: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
