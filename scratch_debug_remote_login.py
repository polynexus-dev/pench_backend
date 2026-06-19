import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://nagpur.pench.api.polynexus.in/api/accounts/login/"
payload = {"username": "admin", "password": "admin"}
try:
    response = requests.post(url, json=payload, verify=False, timeout=10)
    print("Status Code:", response.status_code)
    print("Content Type:", response.headers.get("Content-Type"))
    print("Response Text (first 500 chars):")
    print(response.text[:500])
except Exception as e:
    print("Error:", e)
