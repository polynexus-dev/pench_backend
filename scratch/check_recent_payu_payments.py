import psycopg2

conn = psycopg2.connect(
    "dbname=delivery_erp_dev user=postgres password=admin host=localhost port=5432"
)
cur = conn.cursor()

for schema in ["nagpur", "pench-nagpur", "pune"]:
    cur.execute(
        f"""
        SELECT p.id, p.created_at, p.amount, p.purpose, p.status,
               p.payment_gateway, p.gateway_txnid, p.gateway_mihpayid,
               p.gateway_mode, p.transaction_id, p.verified_at,
               p.order_id, p.bill_id, p.subscription_id,
               c.name, c.phone
        FROM "{schema}".finance_onlinepayment p
        JOIN "{schema}".crm_customer c ON p.customer_id = c.id
        ORDER BY p.created_at DESC
        LIMIT 10;
        """
    )
    rows = cur.fetchall()
    if rows:
        print(f"=== OnlinePayments in [{schema}] ===")
        for r in rows:
            print(
                f"  ID: {r[0]} | Created: {r[1]} | Customer: {r[14]} ({r[15]})\n"
                f"  Amount: INR {r[2]} | Purpose: {r[3]} | Status: {r[4]} | Gateway: {r[5]}\n"
                f"  TxnID: {r[6]} | MihPayID: {r[7]} | Mode: {r[8]} | BankRef: {r[9]} | VerifiedAt: {r[10]}\n"
                f"  OrderID: {r[11]} | BillID: {r[12]} | SubID: {r[13]}"
            )
            if r[11]:
                cur.execute(
                    f'SELECT status, payment_status, payment_method, amount_collected, payment_transaction_id FROM "{schema}".orders_order WHERE id = %s;',
                    (r[11],),
                )
                print("  -> Linked Order State:", cur.fetchone())
            if r[12]:
                cur.execute(
                    f'SELECT invoice_number, total_amount, amount_paid, status FROM "{schema}".finance_monthlybill WHERE id = %s;',
                    (r[12],),
                )
                print("  -> Linked Bill State:", cur.fetchone())
                cur.execute(
                    f'SELECT id, amount, payment_method, transaction_id, notes FROM "{schema}".finance_transaction WHERE bill_id = %s ORDER BY payment_date DESC;',
                    (r[12],),
                )
                print("  -> Linked Bill Transactions:", cur.fetchall())
            if r[13]:
                cur.execute(
                    f'SELECT id, status, frequency FROM "{schema}".subscriptions_subscription WHERE id = %s;',
                    (r[13],),
                )
                print("  -> Linked Subscription State:", cur.fetchone())

