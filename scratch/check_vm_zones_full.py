import requests
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URLS = [
    "https://pench-nagpur.pench.api.polynexus.in",
    "https://nagpur.pench.api.polynexus.in",
    "http://13.235.143.251",
    "http://13.235.143.251:8000"
]

def check_vm_zones():
    session = requests.Session()
    working_base = None
    token = None

    for base_url in BASE_URLS:
        try:
            print(f"Trying to connect to {base_url}...")
            login_url = f"{base_url}/api/accounts/login/"
            resp = session.post(login_url, json={"username": "admin", "password": "admin"}, verify=False, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access") or data.get("token") or data.get("tokens", {}).get("access")
                if token:
                    working_base = base_url
                    print(f"Successfully logged in at {base_url}!")
                    break
        except Exception as e:
            print(f"Failed to connect to {base_url}: {e}")

    if not working_base or not token:
        print("ERROR: Could not authenticate on any VM endpoint.")
        return

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Fetch Zones
    print(f"\n--- Fetching Zones from {working_base}/api/ems/zones/ ---")
    z_res = session.get(f"{working_base}/api/ems/zones/", headers=headers, verify=False, timeout=10)
    print(f"Status Code: {z_res.status_code}")
    
    if z_res.status_code != 200:
        print("Failed to fetch zones. Response:", z_res.text[:500])
        return

    zones_data = z_res.json()
    zones = zones_data.get("results") if isinstance(zones_data, dict) and "results" in zones_data else zones_data

    # Fetch Drivers to map names
    d_res = session.get(f"{working_base}/api/ems/drivers/", headers=headers, verify=False, timeout=10)
    drivers = d_res.json().get("results") if isinstance(d_res.json(), dict) and "results" in d_res.json() else d_res.json() if d_res.status_code == 200 else []
    
    driver_map = {}
    if isinstance(drivers, list):
        for d in drivers:
            d_id = d.get("id")
            user_id = d.get("user")
            driver_map[d_id] = d
            if user_id:
                driver_map[f"user_{user_id}"] = d

    # Fetch Customers to count customers per zone
    c_res = session.get(f"{working_base}/api/erp/customers/?limit=1000", headers=headers, verify=False, timeout=10)
    customers = c_res.json().get("results") if isinstance(c_res.json(), dict) and "results" in c_res.json() else c_res.json() if c_res.status_code == 200 else []

    zone_customer_counts = {}
    if isinstance(customers, list):
        for c in customers:
            z = c.get("zone")
            z_id = z.get("id") if isinstance(z, dict) else z
            if z_id:
                zone_customer_counts[z_id] = zone_customer_counts.get(z_id, 0) + 1

    print(f"\nFound {len(zones) if isinstance(zones, list) else 0} zone(s):\n")

    if isinstance(zones, list):
        for i, z in enumerate(zones, 1):
            z_id = z.get("id")
            name = z.get("name")
            code = z.get("code") or z.get("zone_code")
            driver_id = z.get("assigned_driver")
            driver_name = z.get("driver_name")
            num_cust = zone_customer_counts.get(z_id, 0)
            boundary = z.get("boundary")
            
            print(f"[{i}] Zone Name: '{name}'")
            print(f"    - ID: {z_id}")
            if code:
                print(f"    - Code: {code}")
            print(f"    - Assigned Driver ID: {driver_id} (Driver Name: {driver_name or 'N/A'})")
            print(f"    - Customer Count: {num_cust}")
            if boundary:
                b_str = json.dumps(boundary)
                if len(b_str) > 120:
                    b_str = b_str[:120] + "... (truncated)"
                print(f"    - Boundary Data: {b_str}")
            print("-" * 60)

if __name__ == "__main__":
    check_vm_zones()
