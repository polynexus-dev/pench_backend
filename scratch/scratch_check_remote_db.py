import psycopg

try:
    print("Connecting to remote database on VM...")
    conn = psycopg.connect(
        dbname="delivery_erp",
        user="postgres",
        password="admin",
        host="13.235.143.251",
        port="5433",
        connect_timeout=5
    )
    print("Connection successful!")
    
    with conn.cursor() as cursor:
        # Check schemas
        cursor.execute("SELECT schema_name FROM information_schema.schemata;")
        schemas = [row[0] for row in cursor.fetchall()]
        print(f"Available schemas: {schemas}")
        
        # Check django_migrations for tenants in public schema
        cursor.execute("""
            SELECT name, applied 
            FROM public.django_migrations 
            WHERE app = 'tenants' 
            ORDER BY applied;
        """)
        migrations = cursor.fetchall()
        print(f"tenants migrations in public schema: {migrations}")
        
        # Check all migration records in public schema
        cursor.execute("""
            SELECT app, name, applied 
            FROM public.django_migrations 
            ORDER BY applied;
        """)
        all_migrations = cursor.fetchall()
        print(f"All migrations in public schema: {all_migrations}")
        
        # Check tables in public schema
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public';
        """)
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tables in public schema: {tables}")

    conn.close()

except Exception as e:
    print(f"Connection failed: {e}")
