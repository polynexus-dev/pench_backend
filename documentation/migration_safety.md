# Migration Safety Guide

Working with multi-tenant databases requires extra care during migrations. This guide explains how to avoid common pitfalls.

## 1. Shared vs. Tenant Apps
Ensure every app is correctly categorized in `settings.py`:
- **SHARED_APPS**: Models that exist in the `public` schema only (e.g., `City`, `User`).
- **TENANT_APPS**: Models that exist in every tenant schema (e.g., `Order`, `Customer`).

> [!WARNING]
> Never put the same app in both lists unless specifically required (like `contenttypes`), as this can lead to duplicate tables and migration conflicts.

## 2. Safe Migration Workflow

Always follow these steps when changing models:

1.  **Local Development**:
    ```bash
    python manage.py makemigrations
    python manage.py migrate_schemas --shared
    python manage.py migrate_schemas --tenant
    ```
2.  **Commit Migrations**: Always commit the `.py` files in the `migrations/` folder.
3.  **CI/CD & Docker**: The `entrypoint.sh` automatically runs these commands. If a migration is missing, the server will log an error.

## 3. Common Troubleshooting

### "Table already exists"
This happens if a migration was partially applied or if a schema was created manually.
**Solution**: Use `python manage.py migrate_schemas --tenant --fake` if you are sure the DB matches the code.

### "Relation does not exist"
Usually means a tenant app is trying to access a shared model that hasn't been migrated yet, or vice versa.
**Solution**: Ensure `--shared` is run before `--tenant`.

### Syncing Inconsistent Tenants
If you suspect some tenants are out of sync:
```bash
python manage.py verify_tenants
```

## 4. Production Rules
- **Backup**: Always backup the DB before running complex migrations on a VM/Production.
- **Atomic**: Django runs migrations in transactions by default, but be careful with `RunPython` operations that might fail mid-way.
