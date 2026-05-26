import requests
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://nagpur.pench.api.polynexus.in"


def inspect_zones():
    session = requests.Session()

    # Login
    login_url = f"{BASE_URL}/api/accounts/login/"
    login_payload = {"username": "admin", "password": "admin"}
    response = session.post(login_url, json=login_payload, verify=False, timeout=10)
    token = (
        response.json().get("access")
        or response.json().get("token")
        or response.json().get("tokens", {}).get("access")
    )

    if not token:
        print("Failed to login.")
        return

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Get Zones
    zones_response = session.get(
        f"{BASE_URL}/api/ems/zones/", headers=headers, verify=False, timeout=10
    )
    zones = zones_response.json()

    print("=== ZONE BOUNDARIES ===")
    if isinstance(zones, list):
        for z in zones:
            print(f"Zone Name: {z.get('name')}")
            print(f"  ID: {z.get('id')}")
            print(f"  Boundary: {json.dumps(z.get('boundary'))}")
            print("-" * 50)
    else:
        print("Zones response is not a list:", zones)


if __name__ == "__main__":
    inspect_zones()
