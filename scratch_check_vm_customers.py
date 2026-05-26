import requests
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://nagpur.pench.api.polynexus.in"

def run():
    session = requests.Session()
    login_url = f"{BASE_URL}/api/accounts/login/"
    response = session.post(login_url, json={"username": "admin", "password": "admin"}, verify=False, timeout=10)
    token = response.json().get("access") or response.json().get("tokens", {}).get("access")
    
    if not token:
        print("Failed to login.")
        return
        
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Fetch customers
    cust_res = session.get(f"{BASE_URL}/api/erp/customers/", headers=headers, verify=False)
    print(f"Customers Status: {cust_res.status_code}")
    print(f"Customers Response: {cust_res.text[:1000]}")
    
    # Try querying by QR code ID directly if there's a filter
    cust_filter_res = session.get(f"{BASE_URL}/api/erp/customers/?qr_code_id=c4ed832a-4844-42ed-8519-d205283f3b8d", headers=headers, verify=False)
    print(f"Filtered Customers Status: {cust_filter_res.status_code}")
    print(f"Filtered Customers Response: {cust_filter_res.text[:1000]}")

if __name__ == '__main__':
    run()
