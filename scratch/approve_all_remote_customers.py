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
    
    print("\nFetching Customers...")
    cust_res = requests.get(f"{BASE_URL}/api/erp/customers/?limit=1000", headers=headers, verify=False, timeout=10)
    print(f"Status: {cust_res.status_code}")
    customers = cust_res.json()
    if isinstance(customers, dict) and "results" in customers:
        customers = customers["results"]
    
    trial_customers = [c for c in customers if c.get('is_new') and not c.get('trial_approved')]
    print(f"Found {len(trial_customers)} unapproved trial customers.")
    
    approved_count = 0
    failed_count = 0
    
    for c in trial_customers:
        c_id = c.get('id')
        name = c.get('name')
        print(f"Approving customer: {name} (ID: {c_id})...")
        approve_url = f"{BASE_URL}/api/erp/customers/{c_id}/approve/"
        res = requests.post(approve_url, headers=headers, verify=False, timeout=10)
        if res.status_code == 200:
            print(f"  SUCCESS: {name} approved.")
            approved_count += 1
        else:
            print(f"  FAILED: Status {res.status_code} - {res.text[:200]}")
            failed_count += 1
            
    print(f"\nCompleted approval. Approved: {approved_count}, Failed: {failed_count}")

if __name__ == "__main__":
    main()
