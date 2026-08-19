import requests
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://pench-nagpur.pench.api.polynexus.in"

accounts_to_test = [
    {"role": "Admin / ERP", "username": "admin", "password": "admin"},
    {"role": "ERP Manager", "username": "erp_manager", "password": "password123"},
    {"role": "Delivery Driver", "username": "delivery_driver", "password": "password123"},
    {"role": "CRM Customer", "username": "crm_customer", "password": "password123"},
    {"role": "Customer (Phone OTP)", "phone": "9000000003"},
]

print("=== TESTING GOOGLE PLAY TEST ACCOUNTS ON VM SERVER ===")

for acc in accounts_to_test:
    print(f"\nTesting {acc['role']}...")
    if "username" in acc:
        login_url = f"{BASE_URL}/api/accounts/login/"
        payload = {"username": acc["username"], "password": acc["password"]}
        try:
            res = requests.post(login_url, json=payload, verify=False, timeout=10)
            print(f"Status Code: {res.status_code}")
            if res.status_code == 200:
                data = res.json()
                print(f"LOGIN SUCCESS! User ID: {data.get('user', {}).get('id') or 'N/A'}, Token received: {bool(data.get('access'))}")
            else:
                print(f"LOGIN FAILED: {res.text[:200]}")
        except Exception as e:
            print(f"Error connecting: {e}")
    elif "phone" in acc:
        otp_url = f"{BASE_URL}/api/accounts/request-otp/"
        payload = {"phone": acc["phone"]}
        try:
            res = requests.post(otp_url, json=payload, verify=False, timeout=10)
            print(f"Request OTP Status: {res.status_code}")
            print(f"Response: {res.text[:200]}")
        except Exception as e:
            print(f"Error connecting: {e}")
