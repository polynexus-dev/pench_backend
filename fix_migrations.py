"""
fix_migrations.py
=================
Run this BEFORE `python manage.py runserver` to auto-heal migration state.

What it does:
  1. Detects which schemas exist in PostgreSQL.
  2. Runs makemigrations for all apps (captures any new model changes).
  3. Applies shared (public) migrations with --fake-initial so that
     "relation already exists" errors are skipped gracefully.
  4. Applies tenant-schema migrations the same way.
  5. Prints a clear summary of what was done / skipped.

Usage:
    python fix_migrations.py
    # Then:
    python manage.py runserver 0.0.0.0:8000

Or combine into one command (Windows):
    python fix_migrations.py && python manage.py runserver 0.0.0.0:8000
"""

import os
import sys
import subprocess
import django

# ──────────────────────────────────────────────────────────────────────────────
# Bootstrap Django so we can talk to the DB
# ──────────────────────────────────────────────────────────────────────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection, ProgrammingError, OperationalError  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

SEPARATOR = "=" * 65

def banner(msg: str):
    print(f"\n{SEPARATOR}")
    print(f"  {msg}")
    print(SEPARATOR)

def ok(msg: str):   print(f"  ✅  {msg}")
def skip(msg: str): print(f"  ⏭️   {msg}")
def warn(msg: str): print(f"  ⚠️   {msg}")
def info(msg: str): print(f"  ℹ️   {msg}")
def err(msg: str):  print(f"  ❌  {msg}")


def run(cmd: list[str], description: str) -> bool:
    """Run a manage.py command, return True on success."""
    info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        ok(description)
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                print(f"       {line}")
        return True
    else:
        # Print stderr for debugging
        err(f"FAILED: {description}")
        for line in (result.stderr or result.stdout or "").strip().splitlines():
            print(f"       {line}")
        return False


def table_exists(schema: str, table: str) -> bool:
    """Check if a table exists in the given schema."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass(%s);",
                [f"{schema}.{table}"]
            )
            row = cursor.fetchone()
            return row[0] is not None
    except (ProgrammingError, OperationalError):
        return False


def get_existing_schemas() -> list[str]:
    """Return all non-system schemas in the DB."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name NOT IN ('pg_catalog','information_schema')
                  AND schema_name NOT LIKE 'pg_%'
                ORDER BY schema_name;
                """
            )
            return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        warn(f"Could not list schemas: {e}")
        return ["public"]


def get_tenant_schemas() -> list[str]:
    """
    Return all tenant schema names from the DB.
    Falls back gracefully if the tenants table doesn't exist yet.
    """
    public_tables = get_tables_in_schema("public")
    # Try both possible table names
    for table in ("tenants_city", "tenants_tenant"):
        if table in public_tables:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f'SELECT schema_name FROM public.{table} '
                        f"WHERE schema_name != 'public';"
                    )
                    schemas = [row[0] for row in cursor.fetchall()]
                    if schemas:
                        return schemas
            except Exception:
                pass
    return []


def get_tables_in_schema(schema: str) -> set[str]:
    """Return a set of table names that exist in a given schema."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type = 'BASE TABLE';
                """,
                [schema]
            )
            return {row[0] for row in cursor.fetchall()}
    except Exception:
        return set()


def migration_table_exists(schema: str = "public") -> bool:
    """Check if django_migrations tracking table exists in a schema."""
    return table_exists(schema, "django_migrations")


def has_pending_migrations() -> bool:
    """Return True if there are unapplied migrations (shared or tenant)."""
    result = subprocess.run(
        [sys.executable, "manage.py", "showmigrations", "--plan"],
        capture_output=True, text=True
    )
    return "[ ]" in result.stdout


# ──────────────────────────────────────────────────────────────────────────────
# STEP 1 — Ensure django_migrations table exists (public schema)
# ──────────────────────────────────────────────────────────────────────────────

def ensure_django_migrations_table():
    banner("STEP 1 · Ensure django_migrations table exists")
    if migration_table_exists("public"):
        skip("django_migrations already exists in public schema")
        return

    info("Creating django_migrations table via baseline migrate...")
    # Use --run-syncdb just in case --fake-initial isn't enough on fresh DB
    run(
        [sys.executable, "manage.py", "migrate_schemas",
         "--shared", "--run-syncdb", "--noinput"],
        "Created baseline migration table"
    )


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2 — makemigrations (capture any new model changes)
# ──────────────────────────────────────────────────────────────────────────────

def make_migrations():
    banner("STEP 2 · Detect & generate new migrations (makemigrations)")
    result = subprocess.run(
        [sys.executable, "manage.py", "makemigrations", "--check"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        skip("No new model changes — nothing to generate")
        return

    # There are changes — generate migrations
    success = run(
        [sys.executable, "manage.py", "makemigrations", "--noinput"],
        "Generated new migration files"
    )
    if not success:
        warn("makemigrations had issues — continuing anyway")


# ──────────────────────────────────────────────────────────────────────────────
# STEP 3 — Apply shared (public schema) migrations
# ──────────────────────────────────────────────────────────────────────────────

def apply_shared_migrations():
    banner("STEP 3 · Apply shared (public schema) migrations")

    public_tables = get_tables_in_schema("public")
    # If key tables already exist, use --fake-initial to skip CREATE TABLE errors
    use_fake = bool(public_tables)

    if use_fake:
        info(f"Public schema already has {len(public_tables)} tables → using --fake-initial")
        cmd = [sys.executable, "manage.py", "migrate_schemas",
               "--shared", "--fake-initial", "--noinput"]
    else:
        info("Fresh public schema → running normal migrate")
        cmd = [sys.executable, "manage.py", "migrate_schemas",
               "--shared", "--noinput"]

    success = run(cmd, "Shared migrations applied")

    if not success and not use_fake:
        warn("Normal migrate failed — retrying with --fake-initial")
        run(
            [sys.executable, "manage.py", "migrate_schemas",
             "--shared", "--fake-initial", "--noinput"],
            "Shared migrations applied (fake-initial fallback)"
        )
    elif not success and use_fake:
        warn("--fake-initial also failed — trying without flag as last resort")
        run(
            [sys.executable, "manage.py", "migrate_schemas",
             "--shared", "--noinput"],
            "Shared migrations applied (no-flag fallback)"
        )


# ──────────────────────────────────────────────────────────────────────────────
# STEP 4 — Apply tenant-schema migrations
# ──────────────────────────────────────────────────────────────────────────────

def apply_tenant_migrations():
    banner("STEP 4 · Apply tenant-schema migrations")

    tenant_schemas = get_tenant_schemas()

    if not tenant_schemas:
        skip("No tenant schemas found in DB yet — skipping tenant migrate")
        return

    info(f"Found {len(tenant_schemas)} tenant schema(s): {', '.join(tenant_schemas)}")

    for schema in tenant_schemas:
        tables = get_tables_in_schema(schema)
        use_fake = bool(tables)

        info(f"Schema '{schema}': {len(tables)} tables exist → fake={use_fake}")

        if use_fake:
            cmd = [sys.executable, "manage.py", "migrate_schemas",
                   "--tenant", f"--schema={schema}", "--fake-initial", "--noinput"]
        else:
            cmd = [sys.executable, "manage.py", "migrate_schemas",
                   "--tenant", f"--schema={schema}", "--noinput"]

        success = run(cmd, f"Tenant '{schema}' migrated")

        if not success:
            warn(f"Tenant '{schema}' failed — trying fallback")
            fallback_cmd = [sys.executable, "manage.py", "migrate_schemas",
                            "--tenant", f"--schema={schema}",
                            "--fake-initial", "--noinput"]
            run(fallback_cmd, f"Tenant '{schema}' migrated (fallback)")

    # Also run the bulk command to catch any schemas we might have missed
    info("Running bulk tenant migrate for any remaining schemas...")
    run(
        [sys.executable, "manage.py", "migrate_schemas",
         "--tenant", "--fake-initial", "--noinput"],
        "Bulk tenant migrate complete"
    )


# ──────────────────────────────────────────────────────────────────────────────
# STEP 5 — Final status check
# ──────────────────────────────────────────────────────────────────────────────

def final_check():
    banner("STEP 5 · Final migration status check")
    result = subprocess.run(
        [sys.executable, "manage.py", "showmigrations", "--plan"],
        capture_output=True, text=True
    )
    pending = [l for l in result.stdout.splitlines() if "[ ]" in l]
    applied = [l for l in result.stdout.splitlines() if "[x]" in l]

    ok(f"Applied migrations: {len(applied)}")
    if pending:
        warn(f"Still-pending migrations ({len(pending)}):")
        for p in pending:
            print(f"       {p}")
    else:
        ok("No pending migrations — DB is fully up to date ✨")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'#' * 65}")
    print("  🛠   PENCH BACKEND — Migration Auto-Fix")
    print(f"{'#' * 65}")

    try:
        ensure_django_migrations_table()
        make_migrations()
        apply_shared_migrations()
        apply_tenant_migrations()
        final_check()

        banner("✅  Done — you can now run: python manage.py runserver")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(1)
    except Exception as exc:
        err(f"Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
