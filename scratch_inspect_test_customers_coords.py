import requests
import json
import urllib3

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
    zones_res = session.get(
        f"{BASE_URL}/api/ems/zones/", headers=headers, verify=False, timeout=10
    )
    zones = zones_res.json()
    zones_by_id = {z["id"]: z for z in zones if "id" in z}

    # 3. Get Customers
    customers_res = session.get(
        f"{BASE_URL}/api/erp/customers/", headers=headers, verify=False, timeout=10
    )
    cust_data = customers_res.json()
    customers = cust_data.get("results") if isinstance(cust_data, dict) else cust_data

    print("=== CUSTOMER DETAILS FOR TEST1, TEST2, TEST3 ===")
    if isinstance(customers, list):
        for c in customers:
            zone_id = c.get("zone")
            zone_name = (
                zones_by_id[zone_id].get("name") if zone_id in zones_by_id else "None"
            )
            if zone_name in ["test1", "test2", "test3"]:
                lat = c.get("latitude")
                lon = c.get("longitude")
                print(f"Customer: {c.get('name')}")
                print(f"  Zone: {zone_name}")
                print(f"  Coordinates: Lat={lat}, Lon={lon}")
                print("-" * 40)
    else:
        print("Customers is not a list")


if __name__ == "__main__":
    run_remote_inspect()
