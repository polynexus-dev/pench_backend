import psycopg2

conn = psycopg2.connect(
    "dbname=delivery_erp_dev user=postgres password=admin host=localhost port=5432"
)
cur = conn.cursor()

# List schemas
cur.execute("SELECT schema_name FROM public.tenants_city WHERE schema_name != 'public';")
schemas = [r[0] for r in cur.fetchall()]
print("Tenant Schemas:", schemas)

# List superusers / ERP admins in public.accounts_user
cur.execute(
    "SELECT id, username, phone, email, is_superuser, is_erp_user, is_customer, tenant_schema FROM public.accounts_user ORDER BY id LIMIT 25;"
)
print("\nUsers in public.accounts_user:")
for row in cur.fetchall():
    print(" ", row)

for schema in schemas:
    try:
        cur.execute(
            f"""
            SELECT b.id, b.invoice_number, b.total_amount, b.amount_paid, b.status,
                   c.id, c.name, c.phone, c.email, c.user_id,
                   u.username, u.phone
            FROM "{schema}".finance_monthlybill b
            JOIN "{schema}".crm_customer c ON b.customer_id = c.id
            LEFT JOIN public.accounts_user u ON c.user_id = u.id
            ORDER BY b.created_at DESC
            LIMIT 10;
            """
        )
        rows = cur.fetchall()
        print(f"\nBills in schema [{schema}] ({len(rows)} shown):")
        for r in rows:
            print(
                f"  Bill {r[1]} (id={r[0]}): total={r[2]}, paid={r[3]}, status={r[4]} | "
                f"Customer: {r[6]} (phone={r[7]}, user_id={r[9]}, username={r[10]})"
            )
    except Exception as e:
        conn.rollback()
        print(f"Schema {schema} error:", e)

