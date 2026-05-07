import os
import shutil
from pathlib import Path

def clean_migrations():
    """
    Deletes all migration files except __init__.py in all apps.
    """
    base_dir = Path(__file__).resolve().parent
    apps = [
        'tenants', 'accounts', 'core', 'crm', 'finance', 
        'hr', 'inventory', 'orders', 'routing', 
        'subscriptions', 'taxation', 'tracking'
    ]
    
    for app in apps:
        migration_dir = base_dir / app / 'migrations'
        if migration_dir.exists():
            print(f"Cleaning migrations for {app}...")
            for file in migration_dir.glob('*.py'):
                if file.name != '__init__.py':
                    file.unlink()
            
            # Also clean __pycache__
            pycache = migration_dir / '__pycache__'
            if pycache.exists():
                shutil.rmtree(pycache)

if __name__ == "__main__":
    clean_migrations()
    print("All migrations cleaned. Now run:")
    print("python manage.py makemigrations")
    print("python manage.py migrate_schemas --shared")
    print("python manage.py migrate_schemas --tenant")
