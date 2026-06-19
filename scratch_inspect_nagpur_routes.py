import requests
import json

BASE_URL = "http://127.0.0.1:8000"
headers = {
    "Host": "pench-nagpur.localhost",
    "Content-Type": "application/json"
}

def run_local_inspect():
    session = requests.Session()

    # 1. Login
    login_url = f"{BASE_URL}/api/accounts/login/"
    login_payload = {"username": "admin", "password": "admin"}
    try:
        response = session.post(login_url, json=login_payload, headers=headers, timeout=10)
        token = response.json().get("access") or response.json().get("tokens", {}).get("access")
    except Exception as e:
        print(f"Failed to connect to local server: {e}")
        return

    if not token:
        print("Failed to login to local server. Response:", response.text)
        return

    headers["Authorization"] = f"Bearer {token}"

    # 2. Get Routes for today (2026-06-19)
    print("Fetching routes from local server...")
    routes_res = session.get(
        f"{BASE_URL}/api/erp/orders/routes/?delivery_date=2026-06-19",
        headers=headers,
        timeout=10
    )
    routes = routes_res.json()
    if isinstance(routes, dict):
        routes = routes.get("results", [])
    
    print(f"Found {len(routes)} routes on local server for 2026-06-19.")
    for r in routes:
        print(f"\nRoute ID: {r.get('id')} | Name: {r.get('name')} | Driver: {r.get('driver_name')} | Status: {r.get('status')} | Is Completed: {r.get('is_completed')}")
        stops = r.get("stops", [])
        print(f"Stops count: {len(stops)}")
        for s in stops:
            print(f"  Stop #{s.get('sequence_number')} | Order ID: {s.get('order')} | Cust: {s.get('customer_name')} | Order Status: {s.get('order_status')} | Delivered At: {s.get('delivered_at')}")

if __name__ == "__main__":
    run_local_inspect()
