import requests
import json
import urllib3
import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://nagpur.pench.api.polynexus.in"


def run_remote_inspect():
    session = requests.Session()

    # 1. Login
    login_url = f"{BASE_URL}/api/accounts/login/"
    login_payload = {"username": "admin", "password": "admin"}
    response = session.post(login_url, json=login_payload, verify=False, timeout=10)
    token = (
        response.json().get("access")
        or response.json().get("token")
        or response.json().get("tokens", {}).get("access")
    )

    if not token:
        print("Failed to login to VM.")
        return

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 2. Get Zones
    print("Fetching zones from VM...")
    zones_res = session.get(
        f"{BASE_URL}/api/ems/zones/", headers=headers, verify=False, timeout=10
    )
    zones = zones_res.json()

    # 3. Get Customers
    print("Fetching customers from VM...")
    customers_res = session.get(
        f"{BASE_URL}/api/erp/customers/", headers=headers, verify=False, timeout=10
    )
    cust_data = customers_res.json()
    customers = cust_data.get("results") if isinstance(cust_data, dict) else cust_data

    # 4. Get Orders
    print("Fetching orders from VM...")
    orders_res = session.get(
        f"{BASE_URL}/api/erp/orders/", headers=headers, verify=False, timeout=10
    )
    ord_data = orders_res.json()
    orders = ord_data.get("results") if isinstance(ord_data, dict) else ord_data

    # Map zones by ID
    zones_by_id = {z["id"]: z for z in zones if "id" in z}

    # Map customers by ID
    customers_by_id = {c["id"]: c for c in customers if "id" in c}

    print("\n--- VM ZONES ---")
    for zid, z in zones_by_id.items():
        print(
            f"Zone Name: {z.get('name')}, ID: {zid}, Driver: {z.get('driver_name')} (ID: {z.get('assigned_driver')})"
        )

    print("\n--- VM CUSTOMERS ---")
    for cid, c in customers_by_id.items():
        zone_id = c.get("zone")
        zone_name = (
            zones_by_id[zone_id].get("name") if zone_id in zones_by_id else "None"
        )
        print(
            f"Customer Name: {c.get('name')}, ID: {cid}, Zone: {zone_name} (ID: {zone_id})"
        )

    print("\n--- VM PENDING/CONFIRMED ORDERS ---")
    if isinstance(orders, list):
        for o in orders:
            status = o.get("status")
            if status in ["pending", "confirmed"]:
                cust_val = o.get("customer")
                cust_id = cust_val.get("id") if isinstance(cust_val, dict) else cust_val
                cust_obj = customers_by_id.get(cust_id, {})
                cust_name = cust_obj.get("name", "Unknown")
                zone_id = cust_obj.get("zone")
                zone_name = (
                    zones_by_id[zone_id].get("name")
                    if zone_id in zones_by_id
                    else "None"
                )
                print(
                    f"Order ID: {o.get('id')}, Customer: {cust_name}, Zone: {zone_name}, Date: {o.get('scheduled_delivery_date')}, Status: {status}"
                )
    else:
        print("Orders is not a list:", orders)


if __name__ == "__main__":
    run_remote_inspect()
