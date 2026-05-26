import requests
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://nagpur.pench.api.polynexus.in"


def run():
    session = requests.Session()

    # Try different credentials
    credentials = [
        {"username": "aniket", "password": "password123"},
        {"username": "admin", "password": "admin"},
        {"username": "tom", "password": "password123"},
        {"username": "tom", "password": "password"},
    ]

    token = None
    for creds in credentials:
        login_url = f"{BASE_URL}/api/accounts/login/"
        print(f"Trying login with {creds['username']}...")
        try:
            response = session.post(login_url, json=creds, verify=False, timeout=10)
            print(f"  Status code: {response.status_code}")
            res_json = response.json()
            token = (
                res_json.get("access")
                or res_json.get("token")
                or res_json.get("tokens", {}).get("access")
            )
            if token:
                print(f"  Success! Logged in as {creds['username']}.")
                print(
                    f"  Response user keys: {res_json.get('user', {}).keys() if 'user' in res_json else 'None'}"
                )
                print(f"  Domain Name: {res_json.get('domain_name')}")
                break
        except Exception as e:
            print(f"  Error: {e}")

    if not token:
        print("Failed to login to VM with any credential.")
        return

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Let's test the resolve-qr endpoint on the VM
    qr_id = "c4ed832a-4844-42ed-8519-d205283f3b8d"
    resolve_url = f"{BASE_URL}/api/erp/orders/driver/resolve-qr/{qr_id}/"
    print(f"Calling resolve-qr for {qr_id} on VM...")
    try:
        res = session.get(resolve_url, headers=headers, verify=False, timeout=10)
        print(f"  Status code: {res.status_code}")
        print(f"  Response: {res.text}")
    except Exception as e:
        print(f"  Error calling resolve-qr: {e}")


if __name__ == "__main__":
    run()
