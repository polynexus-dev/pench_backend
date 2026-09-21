import json
import os

target_files = [
    r"c:\Users\admin\Desktop\tejas\Pench\postman_collection (4).json",
    r"c:\Users\admin\Desktop\tejas\Pench\pench_backend\documentation\postman_collection.json"
]

def fix_collection(col):
    # 1. Update variables
    existing_keys = {v.get("key") for v in col.get("variable", [])}
    new_vars = [
        {"key": "refresh_token", "value": "", "type": "string"},
        {"key": "qr_id", "value": "qr_123", "type": "string"},
        {"key": "ws_url", "value": "ws://nagpur.localhost:8000", "type": "string"},
        {"key": "company_id", "value": "", "type": "string"},
        {"key": "city_id", "value": "", "type": "string"},
        {"key": "zone_id", "value": "", "type": "string"},
        {"key": "product_id", "value": "", "type": "string"},
        {"key": "warehouse_id", "value": "", "type": "string"},
        {"key": "driver_user_id", "value": "", "type": "string"},
        {"key": "driver_profile_id", "value": "", "type": "string"},
        {"key": "customer_user_id", "value": "", "type": "string"},
        {"key": "customer_profile_id", "value": "", "type": "string"},
        {"key": "subscription_id", "value": "", "type": "string"},
    ]
    for nv in new_vars:
        if nv["key"] not in existing_keys:
            col["variable"].append(nv)

    # 2. Fix User Registration Templates bodies
    templates_mapping = {
        "Register: SuperAdmin": json.dumps({
            "username": "superadmin",
            "password": "password123",
            "email": "super@example.com",
            "phone": "9100000001",
            "first_name": "Super",
            "last_name": "Admin",
            "role": "SuperAdmin",
            "is_erp_user": True
        }, indent=4),
        "Register: Staff": json.dumps({
            "username": "staffuser",
            "password": "password123",
            "email": "staff@example.com",
            "phone": "9100000002",
            "first_name": "Staff",
            "last_name": "User",
            "role": "Staff",
            "is_erp_user": True
        }, indent=4),
        "Register: Manager": json.dumps({
            "username": "manageruser",
            "password": "password123",
            "email": "manager@example.com",
            "phone": "9100000003",
            "first_name": "Manager",
            "last_name": "User",
            "role": "Manager",
            "is_erp_user": True
        }, indent=4),
        "Register: Driver": json.dumps({
            "username": "driveruser",
            "password": "password123",
            "email": "driver@example.com",
            "phone": "9100000004",
            "first_name": "Driver",
            "last_name": "User",
            "role": "Drivers",
            "is_driver": True,
            "tenant_schema": "nagpur"
        }, indent=4),
        "Register: Customer (Mandatory Fields)": json.dumps({
            "username": "customeruser",
            "password": "password123",
            "email": "customer@example.com",
            "phone": "9100000005",
            "role": "Customers",
            "tenant_schema": "nagpur"
        }, indent=4)
    }

    # Auth token save script
    auth_test_script = {
        "listen": "test",
        "script": {
            "type": "text/javascript",
            "exec": [
                "if (pm.response.code === 200) {",
                "    var jsonData = pm.response.json();",
                "    var token = jsonData.access || jsonData.access_token || (jsonData.tokens && jsonData.tokens.access);",
                "    if (token) {",
                "        pm.environment.set(\"access_token\", token);",
                "        pm.collectionVariables.set(\"access_token\", token);",
                "        console.log(\"Saved access_token:\", token);",
                "    }",
                "    var refresh = jsonData.refresh || jsonData.refresh_token || (jsonData.tokens && jsonData.tokens.refresh);",
                "    if (refresh) {",
                "        pm.environment.set(\"refresh_token\", refresh);",
                "        pm.collectionVariables.set(\"refresh_token\", refresh);",
                "    }",
                "}"
            ]
        }
    }

    def walk_and_fix(items):
        for item in items:
            name = item.get("name", "")
            if "item" in item:
                walk_and_fix(item["item"])
            else:
                req = item.get("request", {})
                
                # Fix registration template bodies
                if name in templates_mapping:
                    req.setdefault("body", {})["mode"] = "raw"
                    req["body"]["raw"] = templates_mapping[name]

                # Add auth token extraction script to login endpoints
                if name in ["POST Standard Login", "POST Login OTP"]:
                    events = item.setdefault("event", [])
                    # check if test event already exists
                    test_ev = next((e for e in events if e.get("listen") == "test"), None)
                    if not test_ev:
                        events.append(auth_test_script)

                # Fix GET Customer QR Code URL from /qr/ to /view-qr/
                if name == "GET Customer QR Code":
                    req["url"]["raw"] = "{{city_url}}/api/erp/customers/{{last_id}}/view-qr/"
                    req["url"]["path"] = ["api", "erp", "customers", "{{last_id}}", "view-qr", ""]

                # Fix WebSocket URL to use ws_url
                if name == "Tracking WebSocket (WS)":
                    req["url"]["raw"] = "{{ws_url}}/ws/tracking/?token={{access_token}}"
                    req["url"]["host"] = ["{{ws_url}}"]
                    req["url"]["path"] = ["ws", "tracking", ""]

    walk_and_fix(col.get("item", []))

    # 3. Inject undelivered endpoints if not present
    driver_folder = next((f for f in col.get("item", []) if f.get("name") == "00. SPECIAL: Driver Mobile App"), None)
    if driver_folder:
        has_submit_undelivered = any(i.get("name") == "POST Submit Undelivered" for i in driver_folder.get("item", []))
        if not has_submit_undelivered:
            driver_folder["item"].append({
                "name": "POST Submit Undelivered",
                "request": {
                    "method": "POST",
                    "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}],
                    "body": {
                        "mode": "formdata",
                        "formdata": [
                            {"key": "pod_image", "type": "file", "src": []},
                            {"key": "pod_latitude", "value": "21.1458", "type": "text"},
                            {"key": "pod_longitude", "value": "79.0882", "type": "text"}
                        ]
                    },
                    "url": {
                        "raw": "{{city_url}}/api/erp/orders/driver/{{last_id}}/submit-undelivered/",
                        "host": ["{{city_url}}"],
                        "path": ["api", "erp", "orders", "driver", "{{last_id}}", "submit-undelivered", ""]
                    }
                },
                "response": []
            })

    logistics_folder = next((f for f in col.get("item", []) if f.get("name") == "05. Logistics & Route Optimization"), None)
    if logistics_folder:
        orders_folder = next((sub for sub in logistics_folder.get("item", []) if sub.get("name") == "Orders (Order)"), None)
        if orders_folder:
            has_mark_undelivered = any(i.get("name") == "POST Mark Undelivered" for i in orders_folder.get("item", []))
            if not has_mark_undelivered:
                orders_folder["item"].append({
                    "name": "POST Mark Undelivered",
                    "request": {
                        "method": "POST",
                        "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}],
                        "body": {
                            "mode": "formdata",
                            "formdata": [{"key": "pod_image", "type": "file", "src": []}]
                        },
                        "url": {
                            "raw": "{{city_url}}/api/erp/orders/{{last_id}}/mark-undelivered/",
                            "host": ["{{city_url}}"],
                            "path": ["api", "erp", "orders", "{{last_id}}", "mark-undelivered", ""]
                        }
                    },
                    "response": []
                })

    # 4. Inject Notifications folder if not present
    has_notifications = any(f.get("name") == "14. Notifications" for f in col.get("item", []))
    if not has_notifications:
        notifications_folder = {
            "name": "14. Notifications",
            "item": [
                {
                    "name": "POST Save FCM Token",
                    "request": {
                        "method": "POST",
                        "header": [
                            {"key": "Authorization", "value": "Bearer {{access_token}}"},
                            {"key": "Content-Type", "value": "application/json"}
                        ],
                        "body": {
                            "mode": "raw",
                            "raw": "{\n    \"token\": \"fcm_device_token_goes_here\"\n}"
                        },
                        "url": {
                            "raw": "{{city_url}}/api/notifications/save-token/",
                            "host": ["{{city_url}}"],
                            "path": ["api", "notifications", "save-token", ""]
                        }
                    },
                    "response": []
                },
                {
                    "name": "GET List FCM Tokens",
                    "request": {
                        "method": "GET",
                        "header": [
                            {"key": "Authorization", "value": "Bearer {{access_token}}"}
                        ],
                        "url": {
                            "raw": "{{city_url}}/api/notifications/tokens/",
                            "host": ["{{city_url}}"],
                            "path": ["api", "notifications", "tokens", ""]
                        }
                    },
                    "response": []
                },
                {
                    "name": "DELETE FCM Token",
                    "request": {
                        "method": "DELETE",
                        "header": [
                            {"key": "Authorization", "value": "Bearer {{access_token}}"}
                        ],
                        "url": {
                            "raw": "{{city_url}}/api/notifications/tokens/{{last_id}}/",
                            "host": ["{{city_url}}"],
                            "path": ["api", "notifications", "tokens", "{{last_id}}", ""]
                        }
                    },
                    "response": []
                }
            ]
        }
        col["item"].append(notifications_folder)

    return col

for fp in target_files:
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        data = fix_collection(data)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Successfully fixed and updated {fp}")
