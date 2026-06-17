import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://pench-nagpur.pench.api.polynexus.in"

def main():
    print("Logging in to remote API...")
    login_url = f"{BASE_URL}/api/accounts/login/"
    login_response = requests.post(login_url, json={"username": "admin", "password": "admin"}, verify=False, timeout=10)
    
    if login_response.status_code != 200:
        print(f"Login failed! Status: {login_response.status_code}")
        print(login_response.text)
        return
        
    token = login_response.json()["access"]
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\nTriggering Route Regeneration for 2026-06-17...")
    url = f"{BASE_URL}/api/erp/orders/routes/regenerate/"
    payload = {"date": "2026-06-17"}
    res = requests.post(url, json=payload, headers=headers, verify=False, timeout=30)
    
    print(f"Status Code: {res.status_code}")
    try:
        print("Response JSON:")
        import json
        print(json.dumps(res.json(), indent=2))
    except Exception as e:
        print(f"Failed to parse response JSON: {e}")
        print(res.text[:1000])

if __name__ == "__main__":
    main()
