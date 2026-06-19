import requests
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://pench-nagpur.pench.api.polynexus.in"

def run_remote_inspect():
    session = requests.Session()

    # 1. Login
    login_url = f"{BASE_URL}/api/accounts/login/"
    login_payload = {"username": "admin", "password": "admin"}
    response = session.post(login_url, json=login_payload, verify=False, timeout=10)
    token = response.json().get("access") or response.json().get("tokens", {}).get("access")

    if not token:
        print("Failed to login to VM.")
        return

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 2. Get Routes
    print("Fetching routes from VM...")
    # Let's fetch all routes or routes for recent dates. We don't filter to get a complete view.
    routes_res = session.get(
        f"{BASE_URL}/api/erp/orders/routes/", headers=headers, verify=False, timeout=10
    )
    res_data = routes_res.json()
    routes = res_data.get("results") if isinstance(res_data, dict) else res_data

    print(f"\n=== ROUTES ON VM (Total: {len(routes) if isinstance(routes, list) else 0}) ===")
    if isinstance(routes, list):
        for r in routes:
            print(f"\nRoute ID: {r.get('id')} | Name: {r.get('name')} | Date: {r.get('delivery_date')} | Driver: {r.get('driver_name')} | Status: {r.get('status')} | Completed: {r.get('is_completed')}")
            stops = r.get("stops", [])
            print(f"Stops count: {len(stops)}")
            for s in stops:
                print(f"  Stop #{s.get('sequence_number')} | Order ID: {s.get('order')} | Cust: {s.get('customer_name')} | Order Status: {s.get('order_status')} | Delivered At: {s.get('delivered_at')}")
    else:
        print("Routes is not a list:", routes)

if __name__ == "__main__":
    run_remote_inspect()
