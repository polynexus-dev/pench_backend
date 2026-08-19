import requests
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://pench-nagpur.pench.api.polynexus.in"

# 1. Login as Admin
login_url = f"{BASE_URL}/api/accounts/login/"
login_payload = {"username": "admin", "password": "admin"}

print("=== LOGGING IN AS ADMIN ON VM ===")
res = requests.post(login_url, json=login_payload, verify=False, timeout=10)
if res.status_code != 200:
    print(f"Failed to log in as admin: {res.text}")
    exit(1)

token = res.json().get("access")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
print("Admin login successful!")

# 2. Register / Create Test Accounts
test_accounts = [
    {
        "username": "google_test_customer",
        "email": "google_customer@pench.in",
        "password": "GoogleTest@2026",
        "phone": "9999000001",
        "first_name": "Google",
        "last_name": "Reviewer Customer",
        "is_customer": True,
        "is_driver": False,
        "is_erp_user": False,
        "tenant_schema": "pench-nagpur",
        "role": "Customer"
    },
    {
        "username": "google_test_driver",
        "email": "google_driver@pench.in",
        "password": "GoogleTest@2026",
        "phone": "9999000002",
        "first_name": "Google",
        "last_name": "Reviewer Driver",
        "is_customer": False,
        "is_driver": True,
        "is_erp_user": False,
        "tenant_schema": "pench-nagpur",
        "role": "Driver"
    },
    {
        "username": "google_test_admin",
        "email": "google_admin@pench.in",
        "password": "GoogleTest@2026",
        "phone": "9999000003",
        "first_name": "Google",
        "last_name": "Reviewer Admin",
        "is_customer": False,
        "is_driver": False,
        "is_erp_user": True,
        "tenant_schema": "pench-nagpur",
        "role": "SuperAdmin"
    }
]

create_user_url = f"{BASE_URL}/api/accounts/users/"

for acc in test_accounts:
    print(f"\nCreating account: {acc['username']} ({acc['role']})...")
    resp = requests.post(create_user_url, json=acc, headers=headers, verify=False, timeout=10)
    print(f"Status: {resp.status_code}")
    if resp.status_code in [200, 201]:
        print(f"SUCCESS: {acc['username']} created!")
    else:
        print(f"Response: {resp.text[:300]}")

# 3. Verify Login for each newly created account
print("\n=== VERIFYING LOGIN FOR NEW GOOGLE TEST ACCOUNTS ===")
for acc in test_accounts:
    print(f"Verifying {acc['username']}...")
    login_resp = requests.post(login_url, json={"username": acc["username"], "password": acc["password"]}, verify=False, timeout=10)
    if login_resp.status_code == 200:
        u_data = login_resp.json()
        print(f"  -> LOGIN OK! Token: {bool(u_data.get('access'))}")
    else:
        print(f"  -> LOGIN FAILED: {login_resp.text[:200]}")
