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
    
    print("\n0. Fetching Users...")
    users_res = requests.get(f"{BASE_URL}/api/accounts/users/?limit=1000", headers=headers, verify=False, timeout=10)
    users_list = []
    if users_res.status_code == 200:
        users_list = users_res.json()
        if isinstance(users_list, dict) and "results" in users_list:
            users_list = users_list["results"]
    user_map = {u["id"]: u["username"] for u in users_list if "id" in u}
    print(f"Fetched {len(user_map)} users from auth.")

    print("\n1. Fetching Warehouses...")
    wh_res = requests.get(f"{BASE_URL}/api/erp/inventory/warehouses/", headers=headers, verify=False, timeout=10)
    print(f"Status: {wh_res.status_code}")
    warehouses = wh_res.json()
    if isinstance(warehouses, dict) and "results" in warehouses:
        warehouses = warehouses["results"]
    for w in warehouses:
        print(f"  Warehouse ID: {w.get('id')} | Name: {w.get('name')} | Lat/Lng: {w.get('latitude')}, {w.get('longitude')}")

    print("\n2. Fetching Drivers...")
    dr_res = requests.get(f"{BASE_URL}/api/ems/drivers/", headers=headers, verify=False, timeout=10)
    print(f"Status: {dr_res.status_code}")
    drivers = dr_res.json()
    if isinstance(drivers, dict) and "results" in drivers:
        drivers = drivers["results"]
    for d in drivers:
        user_id = d.get('user')
        username = user_map.get(user_id, f"Unknown (ID: {user_id})")
        
        # Check warehouse info - warehouse can be an ID or an object depending on serializer
        wh = d.get('warehouse')
        wh_name = "None"
        if isinstance(wh, dict):
            wh_name = wh.get('name')
        elif wh is not None:
            # find warehouse by ID
            wh_obj = next((w for w in warehouses if w.get('id') == wh), None)
            if wh_obj:
                wh_name = wh_obj.get('name')
            else:
                wh_name = f"Warehouse ID: {wh}"
                
        print(f"  Driver ID: {d.get('id')} | User: {username} (ID: {user_id}) | Warehouse: {wh_name} | Available: {d.get('is_available')}")

    print("\n3. Fetching Zones...")
    z_res = requests.get(f"{BASE_URL}/api/ems/zones/", headers=headers, verify=False, timeout=10)
    print(f"Status: {z_res.status_code}")
    zones = z_res.json()
    if isinstance(zones, dict) and "results" in zones:
        zones = zones["results"]
    for z in zones:
        driver_user_id = z.get('assigned_driver')
        driver_username = user_map.get(driver_user_id, "None")
        print(f"  Zone ID: {z.get('id')} | Name: {z.get('name')} | Assigned Driver User: {driver_username} (ID: {driver_user_id})")

    print("\n4. Fetching Customers...")
    cust_res = requests.get(f"{BASE_URL}/api/erp/customers/?limit=1000", headers=headers, verify=False, timeout=10)
    print(f"Status: {cust_res.status_code}")
    customers = cust_res.json()
    if isinstance(customers, dict) and "results" in customers:
        customers = customers["results"]
    
    customers_with_zone = 0
    customers_new_unapproved = 0
    zone_counts = {}
    
    for c in customers:
        zone = c.get('zone')
        is_new = c.get('is_new', False)
        trial_approved = c.get('trial_approved', False)
        
        if zone:
            customers_with_zone += 1
            zname = zone.get('name') if isinstance(zone, dict) else f"Zone ID: {zone}"
            zone_counts[zname] = zone_counts.get(zname, 0) + 1
            
        if is_new and not trial_approved:
            customers_new_unapproved += 1
            
    print(f"  Total Customers Fetched: {len(customers)}")
    print(f"  Customers with Zone assigned: {customers_with_zone}")
    print(f"  New Unapproved Trial Customers: {customers_new_unapproved}")
    print(f"  Customer distribution by zone: {zone_counts}")

    print("\n5. Fetching Pending/Confirmed Orders for 2026-06-17...")
    orders_res = requests.get(f"{BASE_URL}/api/erp/orders/?limit=1000&scheduled_delivery_date=2026-06-17", headers=headers, verify=False, timeout=10)
    print(f"Status: {orders_res.status_code}")
    orders = orders_res.json()
    if isinstance(orders, dict) and "results" in orders:
        orders = orders["results"]
        
    print(f"  Total Orders Fetched for 2026-06-17: {len(orders)}")
    
    # Analyze if orders can map to route:
    unmapped_reasons = {}
    for o in orders:
        c = o.get('customer')
        if not c:
            unmapped_reasons["No customer on order"] = unmapped_reasons.get("No customer on order", 0) + 1
            continue
            
        # customer field in order response could be ID or dict. If it is ID, we should fetch/resolve or assume details
        if isinstance(c, (int, str)):
            # find customer in customers list
            c_obj = next((cust for cust in customers if str(cust.get('id')) == str(c)), None)
            if not c_obj:
                unmapped_reasons["Customer details not found in cache"] = unmapped_reasons.get("Customer details not found in cache", 0) + 1
                continue
            c = c_obj
            
        zone = c.get('zone')
        is_new = c.get('is_new', False)
        trial_approved = c.get('trial_approved', False)
        
        if not zone:
            unmapped_reasons["Customer has no zone"] = unmapped_reasons.get("Customer has no zone", 0) + 1
            continue
            
        if is_new and not trial_approved:
            unmapped_reasons["New unapproved trial customer"] = unmapped_reasons.get("New unapproved trial customer", 0) + 1
            continue
            
        # Resolve zone details
        z_id = zone.get('id') if isinstance(zone, dict) else zone
        z_details = next((x for x in zones if x.get('id') == z_id), None)
        if not z_details:
            unmapped_reasons[f"Zone details not found in API list (ID: {z_id})"] = unmapped_reasons.get(f"Zone details not found in API list (ID: {z_id})", 0) + 1
            continue
            
        driver_user_id = z_details.get('assigned_driver')
        if not driver_user_id:
            unmapped_reasons[f"Zone '{z_details.get('name')}' has no primary driver assigned"] = unmapped_reasons.get(f"Zone '{z_details.get('name')}' has no primary driver assigned", 0) + 1
            continue
            
        driver_username = user_map.get(driver_user_id, f"Unknown ID: {driver_user_id}")
        driver_prof = next((x for x in drivers if x.get('user') == driver_user_id), None)
        if not driver_prof:
            unmapped_reasons[f"Driver user '{driver_username}' has no Driver profile"] = unmapped_reasons.get(f"Driver user '{driver_username}' has no Driver profile", 0) + 1
            continue
            
        wh = driver_prof.get('warehouse')
        if not wh:
            unmapped_reasons[f"Driver '{driver_username}' has no associated warehouse"] = unmapped_reasons.get(f"Driver '{driver_username}' has no associated warehouse", 0) + 1
            continue
            
    print(f"  Analysis of why orders cannot be grouped into routes:")
    for reason, count in unmapped_reasons.items():
        print(f"    - {reason}: {count} orders")

if __name__ == "__main__":
    main()
