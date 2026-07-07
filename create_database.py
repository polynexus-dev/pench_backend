import sys
import os
from decouple import config

def main():
    # Load settings from environment/decouple
    db_name = config("DB_NAME", default=None)
    db_user = config("DB_USER", default="postgres")
    db_password = config("DB_PASSWORD", default="")
    db_host = config("DB_HOST", default="localhost")
    db_port = config("DB_PORT", default="5432")

    if not db_name:
        print("ERROR: DB_NAME environment variable is not set. Skipping database creation check.")
        sys.exit(1)

    print(f"Checking if database '{db_name}' exists on {db_host}:{db_port}...")

    # Load PostgreSQL driver (support psycopg3 and psycopg2)
    try:
        import psycopg as pg
    except ImportError:
        try:
            import psycopg2 as pg
        except ImportError:
            print("ERROR: Neither 'psycopg' (v3) nor 'psycopg2' (v2) is installed. Cannot check/create database.")
            sys.exit(1)

    # 1. Connect to default 'postgres' database to check/create the target database
    try:
        conn = pg.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            dbname="postgres"
        )
        conn.autocommit = True
    except Exception as e:
        print(f"ERROR: Could not connect to PostgreSQL server on '{db_host}:{db_port}' as '{db_user}': {e}")
        sys.exit(1)

    try:
        # Check if database exists
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            exists = cur.fetchone()

        if not exists:
            print(f"Database '{db_name}' does not exist. Creating...")
            # Use Identifier / formatting to safely quote database name in DDL
            if hasattr(pg, 'sql'):
                query = pg.sql.SQL("CREATE DATABASE {}").format(pg.sql.Identifier(db_name))
                with conn.cursor() as cur:
                    cur.execute(query)
            else:
                # Fallback for psycopg2
                with conn.cursor() as cur:
                    cur.execute(f'CREATE DATABASE "{db_name}"')
            print(f"Database '{db_name}' created successfully!")
        else:
            print(f"Database '{db_name}' already exists. Skipping database creation.")

    except Exception as e:
        print(f"ERROR: Failed during database check/creation: {e}")
        conn.close()
        sys.exit(1)
    finally:
        conn.close()

    # 2. Connect to the target database and make sure postgis is enabled
    print(f"Ensuring 'postgis' extension is enabled in database '{db_name}'...")
    try:
        conn_target = pg.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            dbname=db_name
        )
        conn_target.autocommit = True
        with conn_target.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        print("Extension 'postgis' is enabled.")
    except Exception as e:
        print(f"WARNING/ERROR: Could not enable 'postgis' extension in database '{db_name}': {e}")
        print("Note: This is normal if you do not have superuser privileges on the database.")
    finally:
        if 'conn_target' in locals():
            conn_target.close()

if __name__ == "__main__":
    main()
