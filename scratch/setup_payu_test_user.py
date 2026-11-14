import datetime
import hashlib
import base64
import secrets
import uuid
import psycopg2


def make_django_pbkdf2_password(password: str, iterations: int = 870000) -> str:
    salt = secrets.token_hex(11)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    b64_hash = base64.b64encode(dk).decode("ascii").strip()
    return f"pbkdf2_sha256${iterations}${salt}${b64_hash}"


conn = psycopg2.connect(
    "dbname=delivery_erp_dev user=postgres password=admin host=localhost port=5432"
)
conn.autocommit = True
cur = conn.cursor()

# 1. Get all tenant schemas
cur.execute("SELECT schema_name FROM public.tenants_city WHERE schema_name != 'public';")
schemas = [r[0] for r in cur.fetchall()]
print("Tenant schemas:", schemas)

# 2. Apply new PayU columns to finance_onlinepayment in each tenant schema
for schema in schemas:
    cur.execute(
        f"""
        ALTER TABLE "{schema}".finance_onlinepayment
            ALTER COLUMN screenshot DROP NOT NULL;
        ALTER TABLE "{schema}".finance_onlinepayment
            ADD COLUMN IF NOT EXISTS payment_gateway varchar(20) NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS gateway_txnid varchar(100) NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS gateway_mihpayid varchar(100) NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS gateway_mode varchar(30) NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS gateway_raw_response jsonb NOT NULL DEFAULT '{{}}'::jsonb;
        CREATE INDEX IF NOT EXISTS "{schema.replace('-', '_')}_payu_txnid_idx"
            ON "{schema}".finance_onlinepayment (gateway_txnid);
        """
    )
    print(f"Updated finance_onlinepayment table in [{schema}]")

# 3. Create or update Customer User ('customer1' / phone '9876543210' / pass 'pass1234')
pwd_hash = make_django_pbkdf2_password("pass1234")
admin_hash = make_django_pbkdf2_password("admin")

cur.execute("UPDATE public.accounts_user SET password = %s WHERE username = 'admin';", (admin_hash,))

cur.execute("SELECT id FROM public.accounts_user WHERE username = 'customer1' OR phone = '9876543210';")
row = cur.fetchone()
if row:
    user_id = row[0]
    cur.execute(
        """
        UPDATE public.accounts_user
        SET username = 'customer1',
            phone = '9876543210',
            email = 'aniket.customer@penchfoods.com',
            first_name = 'Aniket',
            last_name = 'Sharma',
            password = %s,
            is_customer = TRUE,
            is_active = TRUE,
            tenant_schema = 'nagpur'
        WHERE id = %s;
        """,
        (pwd_hash, user_id),
    )
else:
    cur.execute(
        """
        INSERT INTO public.accounts_user (
            password, is_superuser, username, first_name, last_name, email,
            is_staff, is_active, date_joined, phone, is_erp_user, is_driver,
            is_customer, tenant_schema, portal
        ) VALUES (
            %s, FALSE, 'customer1', 'Aniket', 'Sharma', 'aniket.customer@penchfoods.com',
            FALSE, TRUE, NOW(), '9876543210', FALSE, FALSE,
            TRUE, 'nagpur', 'customer'
        ) RETURNING id;
        """,
        (pwd_hash,),
    )
    user_id = cur.fetchone()[0]

print(f"\nCustomer User Ready -> id={user_id}, username='customer1', phone='9876543210', password='pass1234'")

# 4. Seed Customer profile + MonthlyBills + Order + Subscription in 'nagpur' and 'pench-nagpur'
today = datetime.date.today()
curr_month = datetime.date(today.year, today.month, 1)
prev_month = (curr_month - datetime.timedelta(days=1)).replace(day=1)

for schema in ["nagpur", "pench-nagpur"]:
    if schema not in schemas:
        continue

    cur.execute(
        f'SELECT id FROM "{schema}".crm_customer WHERE phone = %s OR user_id = %s LIMIT 1;',
        ("9876543210", user_id),
    )
    cust_row = cur.fetchone()
    if cust_row:
        cust_id = cust_row[0]
        cur.execute(
            f"""
            UPDATE "{schema}".crm_customer
            SET name = 'Aniket Sharma',
                phone = '9876543210',
                email = 'aniket.customer@penchfoods.com',
                user_id = %s,
                is_active = TRUE,
                is_new = FALSE,
                trial_approved = TRUE
            WHERE id = %s;
            """,
            (user_id, cust_id),
        )
    else:
        cust_id = str(uuid.uuid4())
        qr_id = str(uuid.uuid4())
        cur.execute(
            f"""
            INSERT INTO "{schema}".crm_customer (
                id, created_at, updated_at, name, company, email, phone,
                address, notes, is_active, is_new, trial_approved, qr_code_id, user_id
            ) VALUES (
                %s, NOW(), NOW(), 'Aniket Sharma', '', 'aniket.customer@penchfoods.com', '9876543210',
                'Plot 12, Dharampeth, Nagpur', '', TRUE, FALSE, TRUE, %s, %s
            );
            """,
            (cust_id, qr_id, user_id),
        )

    # Seed Bill 1 (Unpaid - INR 1500.00)
    inv1 = f"INV-{schema[:3].upper()}-202611-01"
    cur.execute(
        f'SELECT id FROM "{schema}".finance_monthlybill WHERE customer_id = %s AND billing_month = %s;',
        (cust_id, curr_month),
    )
    b1 = cur.fetchone()
    if not b1:
        b1_id = str(uuid.uuid4())
        cur.execute(
            f"""
            INSERT INTO "{schema}".finance_monthlybill (
                id, created_at, updated_at, billing_month, total_amount, amount_paid,
                status, due_date, invoice_number, customer_id
            ) VALUES (%s, NOW(), NOW(), %s, 1500.00, 0.00, 'unpaid', %s, %s, %s);
            """,
            (b1_id, curr_month, today + datetime.timedelta(days=10), inv1, cust_id),
        )
    else:
        b1_id = b1[0]

    # Seed Bill 2 (Partial - Total 2550.00, Paid 1000.00, Remaining 1550.00)
    inv2 = f"INV-{schema[:3].upper()}-202610-02"
    cur.execute(
        f'SELECT id FROM "{schema}".finance_monthlybill WHERE customer_id = %s AND billing_month = %s;',
        (cust_id, prev_month),
    )
    b2 = cur.fetchone()
    if not b2:
        b2_id = str(uuid.uuid4())
        cur.execute(
            f"""
            INSERT INTO "{schema}".finance_monthlybill (
                id, created_at, updated_at, billing_month, total_amount, amount_paid,
                status, due_date, invoice_number, customer_id
            ) VALUES (%s, NOW(), NOW(), %s, 2550.00, 1000.00, 'partial', %s, %s, %s);
            """,
            (b2_id, prev_month, today + datetime.timedelta(days=5), inv2, cust_id),
        )
    else:
        b2_id = b2[0]

    # Seed Special Order (Pending - INR 170.00)
    cur.execute(
        f'SELECT id FROM "{schema}".orders_order WHERE customer_id = %s AND payment_status = %s LIMIT 1;',
        (cust_id, "pending"),
    )
    ord_row = cur.fetchone()
    if not ord_row:
        ord_id = str(uuid.uuid4())
        cur.execute(
            f"""
            INSERT INTO "{schema}".orders_order (
                id, created_at, updated_at, scheduled_delivery_date, status,
                delivery_address, delivery_notes, total, is_special,
                payment_method, amount_collected, payment_transaction_id,
                payment_status, arriving_notification_sent, customer_id
            ) VALUES (
                %s, NOW(), NOW(), %s, 'pending',
                'Plot 12, Dharampeth, Nagpur', '', 170.00, TRUE,
                'payu', 0.00, '', 'pending', FALSE, %s
            );
            """,
            (ord_id, today + datetime.timedelta(days=1), cust_id),
        )
    else:
        ord_id = ord_row[0]

    print(f"\nSchema [{schema}] records for Customer 'Aniket Sharma' (customer_id={cust_id}):")
    print(f"  1. Unpaid Monthly Bill:  {inv1} | Remaining: INR 1500.00 | Bill UUID: {b1_id}")
    print(f"  2. Partial Monthly Bill: {inv2} | Remaining: INR 1550.00 | Bill UUID: {b2_id}")
    print(f"  3. Special Order:        INR 170.00 (pending)            | Order UUID: {ord_id}")
