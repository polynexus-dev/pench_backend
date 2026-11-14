import datetime
import hashlib
import base64
import json
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

pwd_hash = make_django_pbkdf2_password("pass1234")
today = datetime.date.today()
curr_month = datetime.date(today.year, today.month, 1)
prev_month = (curr_month - datetime.timedelta(days=1)).replace(day=1)

users_spec = [
    {
        "username": "customer2",
        "first_name": "Priya",
        "last_name": "Patil",
        "phone": "9876543211",
        "email": "priya.patil@penchfoods.com",
        "address": "Flat 302, Green Valley, Civil Lines, Nagpur",
        "orders": [
            {"desc": "1x Pure Desi Ghee (500g) + 2x A2 Cow Milk (1L)", "items": [("GHEE-500G", 1, 320.00), ("MILK-A2-1L", 2, 85.00)], "days_ahead": 1},
            {"desc": "2x Fresh Paneer (500g)", "items": [("PANEER-500G", 2, 250.00)], "days_ahead": 2},
        ],
        "bills": [
            {"month": curr_month, "total": 1850.00, "paid": 0.00, "status": "unpaid", "suffix": "201"},
            {"month": prev_month, "total": 2100.00, "paid": 1100.00, "status": "partial", "suffix": "202"},
        ],
        "sub": {"freq": "alternate", "items": [("MILK-A2-1L", 2), ("CURD-500G", 1)]},
    },
    {
        "username": "customer3",
        "first_name": "Rahul",
        "last_name": "Deshmukh",
        "phone": "9876543212",
        "email": "rahul.deshmukh@penchfoods.com",
        "address": "Bungalow 7, Laxmi Nagar, Nagpur",
        "orders": [
            {"desc": "3x A2 Cow Milk (1L) + 2x Farm Fresh Curd (500g)", "items": [("MILK-A2-1L", 3, 85.00), ("CURD-500G", 2, 45.00)], "days_ahead": 1},
            {"desc": "1x Pure Desi Ghee (500g) + 1x Fresh Paneer (500g)", "items": [("GHEE-500G", 1, 320.00), ("PANEER-500G", 1, 250.00)], "days_ahead": 3},
        ],
        "bills": [
            {"month": curr_month, "total": 3200.00, "paid": 0.00, "status": "unpaid", "suffix": "301"},
        ],
        "sub": {"freq": "daily", "items": [("MILK-A2-1L", 3)]},
    },
    {
        "username": "customer4",
        "first_name": "Sneha",
        "last_name": "Kulkarni",
        "phone": "9876543213",
        "email": "sneha.kulkarni@penchfoods.com",
        "address": "Plot 45, Shivaji Nagar, Nagpur",
        "orders": [
            {"desc": "1x Fresh Paneer (500g) + 1x Farm Fresh Curd (500g)", "items": [("PANEER-500G", 1, 250.00), ("CURD-500G", 1, 45.00)], "days_ahead": 1},
            {"desc": "2x Pure Desi Ghee (500g)", "items": [("GHEE-500G", 2, 320.00)], "days_ahead": 2},
        ],
        "bills": [
            {"month": curr_month, "total": 950.00, "paid": 0.00, "status": "unpaid", "suffix": "401"},
            {"month": prev_month, "total": 1400.00, "paid": 500.00, "status": "partial", "suffix": "402"},
        ],
        "sub": {"freq": "weekdays", "items": [("MILK-A2-1L", 1), ("CURD-500G", 1)]},
    },
    {
        "username": "customer5",
        "first_name": "Vikram",
        "last_name": "Joshi",
        "phone": "9876543214",
        "email": "vikram.joshi@penchfoods.com",
        "address": "Row House 9, Ramdaspeth, Nagpur",
        "orders": [
            {"desc": "4x A2 Cow Milk (1L) + 1x Pure Desi Ghee (500g)", "items": [("MILK-A2-1L", 4, 85.00), ("GHEE-500G", 1, 320.00)], "days_ahead": 1},
        ],
        "bills": [
            {"month": curr_month, "total": 4250.00, "paid": 1250.00, "status": "partial", "suffix": "501"},
        ],
        "sub": {"freq": "daily", "items": [("MILK-A2-1L", 2), ("PANEER-500G", 1)]},
    },
    {
        "username": "customer6",
        "first_name": "Kavita",
        "last_name": "Verma",
        "phone": "9876543215",
        "email": "kavita.verma@penchfoods.com",
        "address": "Apartment 104, Pratap Nagar, Nagpur",
        "orders": [
            {"desc": "2x Farm Fresh Curd (500g) + 1x A2 Cow Milk (1L)", "items": [("CURD-500G", 2, 45.00), ("MILK-A2-1L", 1, 85.00)], "days_ahead": 1},
            {"desc": "3x Fresh Paneer (500g) + 1x Pure Desi Ghee (500g)", "items": [("PANEER-500G", 3, 250.00), ("GHEE-500G", 1, 320.00)], "days_ahead": 2},
        ],
        "bills": [
            {"month": curr_month, "total": 1275.00, "paid": 0.00, "status": "unpaid", "suffix": "601"},
        ],
        "sub": {"freq": "weekends", "items": [("MILK-A2-1L", 2), ("GHEE-500G", 1)]},
    },
]

products_catalog = [
    ("MILK-A2-1L", "A2 Cow Milk (1L)", 85.00, "Litre"),
    ("PANEER-500G", "Fresh Paneer (500g)", 250.00, "Pack"),
    ("GHEE-500G", "Pure Desi Ghee (500g)", 320.00, "Jar"),
    ("CURD-500G", "Farm Fresh Curd (500g)", 45.00, "Pack"),
]

# Ensure products exist in nagpur & pench-nagpur
product_ids = {}
for schema in ["nagpur", "pench-nagpur"]:
    product_ids[schema] = {}
    for sku_base, name, price, unit in products_catalog:
        sku = f"{sku_base}-{schema.upper()}"
        cur.execute(f'SELECT id FROM "{schema}".inventory_product WHERE sku = %s LIMIT 1;', (sku,))
        prow = cur.fetchone()
        if prow:
            pid = prow[0]
        else:
            pid = str(uuid.uuid4())
            cur.execute(
                f"""
                INSERT INTO "{schema}".inventory_product (
                    id, created_at, updated_at, name, sku, description,
                    unit_price, unit, is_active, is_returnable
                ) VALUES (%s, NOW(), NOW(), %s, %s, %s, %s, %s, TRUE, FALSE);
                """,
                (pid, name, sku, name, price, unit),
            )
        product_ids[schema][sku_base] = pid

for u in users_spec:
    cur.execute(
        "SELECT id FROM public.accounts_user WHERE username = %s OR phone = %s;",
        (u["username"], u["phone"]),
    )
    row = cur.fetchone()
    if row:
        user_id = row[0]
        cur.execute(
            """
            UPDATE public.accounts_user
            SET username = %s,
                phone = %s,
                email = %s,
                first_name = %s,
                last_name = %s,
                password = %s,
                is_customer = TRUE,
                is_active = TRUE,
                tenant_schema = 'nagpur',
                portal = 'customer'
            WHERE id = %s;
            """,
            (u["username"], u["phone"], u["email"], u["first_name"], u["last_name"], pwd_hash, user_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO public.accounts_user (
                password, is_superuser, username, first_name, last_name, email,
                is_staff, is_active, date_joined, phone, is_erp_user, is_driver,
                is_customer, tenant_schema, portal
            ) VALUES (
                %s, FALSE, %s, %s, %s, %s,
                FALSE, TRUE, NOW(), %s, FALSE, FALSE,
                TRUE, 'nagpur', 'customer'
            ) RETURNING id;
            """,
            (pwd_hash, u["username"], u["first_name"], u["last_name"], u["email"], u["phone"]),
        )
        user_id = cur.fetchone()[0]

    full_name = f"{u['first_name']} {u['last_name']}"
    print(f"\n=======================================================")
    print(f"User: {u['username']} | Phone: {u['phone']} | Pass: pass1234 | Name: {full_name}")

    for schema in ["nagpur", "pench-nagpur"]:
        cur.execute(
            f'SELECT id FROM "{schema}".crm_customer WHERE phone = %s OR user_id = %s LIMIT 1;',
            (u["phone"], user_id),
        )
        crow = cur.fetchone()
        if crow:
            cust_id = crow[0]
            cur.execute(
                f"""
                UPDATE "{schema}".crm_customer
                SET name = %s, phone = %s, email = %s, address = %s, user_id = %s,
                    is_active = TRUE, is_new = FALSE, trial_approved = TRUE
                WHERE id = %s;
                """,
                (full_name, u["phone"], u["email"], u["address"], user_id, cust_id),
            )
        else:
            cust_id = str(uuid.uuid4())
            cur.execute(
                f"""
                INSERT INTO "{schema}".crm_customer (
                    id, created_at, updated_at, name, company, email, phone,
                    address, notes, is_active, is_new, trial_approved, qr_code_id, user_id
                ) VALUES (
                    %s, NOW(), NOW(), %s, '', %s, %s,
                    %s, '', TRUE, FALSE, TRUE, %s, %s
                );
                """,
                (cust_id, full_name, u["email"], u["phone"], u["address"], str(uuid.uuid4()), user_id),
            )

        # Clear previous seeded orders for clean state and insert new distinct orders
        cur.execute(f'DELETE FROM "{schema}".orders_orderitem WHERE order_id IN (SELECT id FROM "{schema}".orders_order WHERE customer_id = %s);', (cust_id,))
        cur.execute(f'DELETE FROM "{schema}".orders_order WHERE customer_id = %s;', (cust_id,))

        for ord_spec in u["orders"]:
            ord_id = str(uuid.uuid4())
            total = sum(qty * price for _, qty, price in ord_spec["items"])
            deliv_date = today + datetime.timedelta(days=ord_spec["days_ahead"])
            cur.execute(
                f"""
                INSERT INTO "{schema}".orders_order (
                    id, created_at, updated_at, scheduled_delivery_date, status,
                    delivery_address, delivery_notes, total, is_special,
                    payment_method, amount_collected, payment_transaction_id,
                    payment_status, arriving_notification_sent, customer_id
                ) VALUES (
                    %s, NOW(), NOW(), %s, 'pending',
                    %s, %s, %s, TRUE,
                    'payu', 0.00, '', 'pending', FALSE, %s
                );
                """,
                (ord_id, deliv_date, u["address"], ord_spec["desc"], total, cust_id),
            )
            for sku_base, qty, price in ord_spec["items"]:
                cur.execute(
                    f"""
                    INSERT INTO "{schema}".orders_orderitem (
                        id, created_at, updated_at, quantity, unit_price, order_id, product_id
                    ) VALUES (%s, NOW(), NOW(), %s, %s, %s, %s);
                    """,
                    (str(uuid.uuid4()), qty, price, ord_id, product_ids[schema][sku_base]),
                )
            if schema == "nagpur":
                print(f"  [Order] INR {total:.2f} — {ord_spec['desc']} (ID: {ord_id})")

        # Bills
        for b_spec in u["bills"]:
            inv_num = f"INV-{schema[:3].upper()}-{b_spec['month'].strftime('%Y%m')}-{b_spec['suffix']}"
            cur.execute(
                f'SELECT id FROM "{schema}".finance_monthlybill WHERE customer_id = %s AND billing_month = %s;',
                (cust_id, b_spec["month"]),
            )
            brow = cur.fetchone()
            if not brow:
                bid = str(uuid.uuid4())
                cur.execute(
                    f"""
                    INSERT INTO "{schema}".finance_monthlybill (
                        id, created_at, updated_at, billing_month, total_amount, amount_paid,
                        status, due_date, invoice_number, customer_id
                    ) VALUES (%s, NOW(), NOW(), %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (bid, b_spec["month"], b_spec["total"], b_spec["paid"], b_spec["status"], today + datetime.timedelta(days=10), inv_num, cust_id),
                )
            else:
                bid = brow[0]
            if schema == "nagpur":
                rem = b_spec["total"] - b_spec["paid"]
                print(f"  [Bill]  {inv_num} ({b_spec['status']}) — Remaining: INR {rem:.2f} (ID: {bid})")

        # Subscription
        cur.execute(f'SELECT id FROM "{schema}".subscriptions_subscription WHERE customer_id = %s LIMIT 1;', (cust_id,))
        srow = cur.fetchone()
        if not srow:
            sid = str(uuid.uuid4())
            cur.execute(
                f"""
                INSERT INTO "{schema}".subscriptions_subscription (
                    id, created_at, updated_at, status, frequency, custom_days,
                    start_date, is_paused, delivery_address, special_instructions, customer_id
                ) VALUES (%s, NOW(), NOW(), 'active', %s, %s, %s, FALSE, %s, '', %s);
                """,
                (sid, u["sub"]["freq"], json.dumps([]), today, u["address"], cust_id),
            )
            for sku_base, qty in u["sub"]["items"]:
                cur.execute(
                    f"""
                    INSERT INTO "{schema}".subscriptions_subscriptionitem (
                        id, created_at, updated_at, quantity, product_id, subscription_id
                    ) VALUES (%s, NOW(), NOW(), %s, %s, %s);
                    """,
                    (str(uuid.uuid4()), qty, product_ids[schema][sku_base], sid),
                )
        else:
            sid = srow[0]
        if schema == "nagpur":
            print(f"  [Sub]   Frequency: {u['sub']['freq']} (ID: {sid})")

