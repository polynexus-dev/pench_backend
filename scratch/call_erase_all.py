import requests
import json
import urllib3
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def main():
    session = requests.Session()
    
    # 1. Login to get token
    login_url = "https://pench.api.polynexus.in/api/accounts/login/"
    login_payload = {"username": "admin", "password": "admin"}
    print(f"Logging in to {login_url}...")
    
    try:
        response = session.post(login_url, json=login_payload, verify=False, timeout=15)
        if response.status_code != 200:
            # Try tenant login URL just in case
            login_url = "https://pench-nagpur.pench.api.polynexus.in/api/accounts/login/"
            print(f"Login failed ({response.status_code}). Trying tenant login at {login_url}...")
            response = session.post(login_url, json=login_payload, verify=False, timeout=15)
            
        response_data = response.json()
        token = (
            response_data.get("access")
            or response_data.get("token")
            or response_data.get("tokens", {}).get("access")
        )
    except Exception as e:
        print(f"Error during login: {e}")
        sys.exit(1)
        
    if not token:
        print(f"Failed to login. Response: {response.status_code} - {response.text}")
        sys.exit(1)
        
    print("Login successful! Token retrieved.")
    
    # 2. Trigger the erase-all endpoint on the public domain
    erase_url = "https://pench.api.polynexus.in/api/erp/tenants/erase-all/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print(f"Sending POST request to {erase_url}...")
    try:
        res = session.post(erase_url, headers=headers, verify=False, timeout=60)
        print(f"Status Code: {res.status_code}")
        print("Response Content:")
        print(json.dumps(res.json(), indent=2))
    except Exception as e:
        print(f"Error calling erase endpoint: {e}")

if __name__ == "__main__":
    main()
