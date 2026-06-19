import requests
import json

BASE_URL = "http://13.235.143.251:8083"

def run_remote_inspect():
    session = requests.Session()

    # 1. Login
    login_url = f"{BASE_URL}/api/accounts/login/"
    login_payload = {"username": "admin", "password": "admin"}
    print(f"Logging in to VM at {login_url}...")
    try:
        response = session.post(login_url, json=login_payload, timeout=10)
        print("Login response status:", response.status_code)
        token = response.json().get("access") or response.json().get("tokens", {}).get("access")
    except Exception as e:
        print(f"Failed to connect to VM: {e}")
        return

    if not token:
        print("Failed to login to VM. Response:", response.text)
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 2. Get Routes for today (2026-06-19)
    print("Fetching routes from VM...")
    routes_res = session.get(
        f"{BASE_URL}/api/erp/orders/routes/?delivery_date=2026-06-19",
        headers=headers,
        timeout=10
    )
    routes = routes_res.json()
    if isinstance(routes, dict):
        routes = routes.get("results", [])
    
    print(f"Found {len(routes)} routes on VM for 2026-06-19.")
    for r in routes:
        print(f"\nRoute ID: {r.get('id')} | Name: {r.get('name')} | Driver: {r.get('driver_name')} | Status: {r.get('status')} | Is Completed: {r.get('is_completed')}")
        stops = r.get("stops", [])
        print(f"Stops count: {len(stops)}")
        for s in stops:
            print(f"  Stop #{s.get('sequence_number')} | Order ID: {s.get('order')} | Cust: {s.get('customer_name')} | Order Status: {s.get('order_status')} | Delivered At: {s.get('delivered_at')}")

if __name__ == "__main__":
    run_remote_inspect()
