import psycopg

try:
    print("Connecting to remote VM database...")
    conn = psycopg.connect(
        dbname="delivery_erp",
        user="postgres",
        password="admin",
        host="13.235.143.251",
        port="5433",
        connect_timeout=10
    )
    print("Connection successful!")
    
    schema = "pench_nagpur"
    with conn.cursor() as cursor:
        # Set search path to Nagpur schema
        cursor.execute(f"SET search_path TO {schema};")
        
        # 1. Fetch routes for 2026-06-19
        cursor.execute("""
            SELECT r.id, r.name, u.username, r.status, r.is_completed, r.started_at, r.completed_at
            FROM orders_route r
            LEFT JOIN accounts_user u ON r.driver_id = u.id
            WHERE r.delivery_date = '2026-06-19';
        """)
        routes = cursor.fetchall()
        print(f"\n=== ROUTES FOR 2026-06-19 in {schema} ===")
        for r in routes:
            r_id, r_name, driver, r_status, r_is_completed, started_at, completed_at = r
            print(f"Route ID: {r_id} | Name: {r_name} | Driver: {driver} | Status: {r_status} | Is Completed: {r_is_completed} | Started At: {started_at} | Completed At: {completed_at}")
            
            # Fetch stops for this route
            cursor.execute("""
                SELECT s.sequence_number, o.id, c.name, o.status, o.delivered_at
                FROM orders_routestop s
                JOIN orders_order o ON s.order_id = o.id
                JOIN crm_customer c ON o.customer_id = c.id
                WHERE s.route_id = %s
                ORDER BY s.sequence_number;
            """, (r_id,))
            stops = cursor.fetchall()
            print(f"Stops count: {len(stops)}")
            for s in stops:
                seq, o_id, cust_name, o_status, o_delivered_at = s
                print(f"  Stop #{seq} | Order ID: {o_id} | Cust: {cust_name} | Status: {o_status} | Delivered At: {o_delivered_at}")

    conn.close()

except Exception as e:
    print(f"Connection failed: {e}")
