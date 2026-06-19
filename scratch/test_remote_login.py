import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://nagpur.pench.api.polynexus.in"

login_url = f"{BASE_URL}/api/accounts/login/"
login_payload = {"username": "admin", "password": "admin"}
response = requests.post(login_url, json=login_payload, verify=False, timeout=10)

print("Status Code:", response.status_code)
print("Response Headers:", response.headers)
try:
    print("Response JSON:", response.json())
except Exception as e:
    print("Not JSON:", e)
    print("Response Text:", response.text[:1000])
