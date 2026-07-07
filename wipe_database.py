import os
import django
import sys

# Set up Django environment
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection

def main():
    print("=== STARTING FULL DATABASE WIPE ===")
    
    with connection.cursor() as cursor:
        # 1. Fetch all schemas that are not system schemas
        cursor.execute("""
            SELECT schema_name 
            FROM information_schema.schemata 
            WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast', 'public') 
            AND schema_name NOT LIKE 'pg_temp_%%' 
            AND schema_name NOT LIKE 'pg_toast_temp_%%';
        """)
        schemas = [row[0] for row in cursor.fetchall()]
        
        # 2. Drop other tenant schemas first
        for schema in schemas:
            print(f"Dropping schema '{schema}'...")
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;')
            
        # 3. Drop public schema
        print("Dropping public schema...")
        cursor.execute("DROP SCHEMA IF EXISTS public CASCADE;")
        
        # 4. Recreate public schema
        print("Recreating public schema...")
        cursor.execute("CREATE SCHEMA public;")
        
        # 5. Enable postgis extension
        print("Enabling postgis extension in public schema...")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        
    print("=== DATABASE WIPE COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    main()
