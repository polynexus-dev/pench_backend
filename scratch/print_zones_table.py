import requests
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://pench-nagpur.pench.api.polynexus.in"

def list_all_zones():
    session = requests.Session()
    login_url = f"{BASE_URL}/api/accounts/login/"
    resp = session.post(login_url, json={"username": "admin", "password": "admin"}, verify=False, timeout=10)
    token = resp.json()["access"]
    headers = {"Authorization": f"Bearer {token}"}

    z_res = session.get(f"{BASE_URL}/api/ems/zones/", headers=headers, verify=False, timeout=10)
    zones = z_res.json()
    if isinstance(zones, dict) and "results" in zones:
        zones = zones["results"]

    c_res = session.get(f"{BASE_URL}/api/erp/customers/?limit=1000", headers=headers, verify=False, timeout=10)
    customers = c_res.json()
    if isinstance(customers, dict) and "results" in customers:
        customers = customers["results"]

    counts = {}
    for c in customers:
        z = c.get("zone")
        zid = z.get("id") if isinstance(z, dict) else z
        if zid:
            counts[zid] = counts.get(zid, 0) + 1

    print(f"Total Zones: {len(zones)}\n")
    print(f"{'#':<3} | {'Zone Name':<35} | {'Zone ID':<38} | {'Assigned Driver':<18} | {'Customers':<10}")
    print("-" * 115)

    for idx, z in enumerate(zones, 1):
        zid = z.get("id")
        name = z.get("name")
        driver_name = z.get("driver_name") or "Unassigned"
        num_c = counts.get(zid, 0)
        print(f"{idx:<3} | {name:<35} | {zid:<38} | {driver_name:<18} | {num_c:<10}")

if __name__ == "__main__":
    list_all_zones()
