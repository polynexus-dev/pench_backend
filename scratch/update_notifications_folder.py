import json
import os

target_files = [
    r"c:\Users\admin\Desktop\tejas\Pench\postman_collection (4).json",
    r"c:\Users\admin\Desktop\tejas\Pench\pench_backend\documentation\postman_collection.json"
]

notifications_items = [
    {
        "name": "GET List In-App Notifications",
        "request": {
            "method": "GET",
            "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}],
            "url": {
                "raw": "{{city_url}}/api/notifications/",
                "host": ["{{city_url}}"],
                "path": ["api", "notifications", ""]
            }
        },
        "response": []
    },
    {
        "name": "POST Mark All Read",
        "request": {
            "method": "POST",
            "header": [
                {"key": "Authorization", "value": "Bearer {{access_token}}"},
                {"key": "Content-Type", "value": "application/json"}
            ],
            "body": {"mode": "raw", "raw": "{}"},
            "url": {
                "raw": "{{city_url}}/api/notifications/read-all/",
                "host": ["{{city_url}}"],
                "path": ["api", "notifications", "read-all", ""]
            }
        },
        "response": []
    },
    {
        "name": "POST Mark Single Read",
        "request": {
            "method": "POST",
            "header": [
                {"key": "Authorization", "value": "Bearer {{access_token}}"},
                {"key": "Content-Type", "value": "application/json"}
            ],
            "body": {"mode": "raw", "raw": "{}"},
            "url": {
                "raw": "{{city_url}}/api/notifications/{{last_id}}/read/",
                "host": ["{{city_url}}"],
                "path": ["api", "notifications", "{{last_id}}", "read", ""]
            }
        },
        "response": []
    },
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
                "raw": "{\n    \"token\": \"fcm_device_registration_token_here\"\n}"
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
            "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}],
            "url": {
                "raw": "{{city_url}}/api/notifications/tokens/",
                "host": ["{{city_url}}"],
                "path": ["api", "notifications", "tokens", ""]
            }
        },
        "response": []
    },
    {
        "name": "POST Send Single Push",
        "request": {
            "method": "POST",
            "header": [
                {"key": "Authorization", "value": "Bearer {{access_token}}"},
                {"key": "Content-Type", "value": "application/json"}
            ],
            "body": {
                "mode": "raw",
                "raw": "{\n    \"token\": \"fcm_device_token\",\n    \"title\": \"Delivery Update\",\n    \"body\": \"Your milk has arrived!\",\n    \"data\": {\n        \"order_id\": \"{{order_id}}\"\n    }\n}"
            },
            "url": {
                "raw": "{{city_url}}/api/notifications/send-single/",
                "host": ["{{city_url}}"],
                "path": ["api", "notifications", "send-single", ""]
            }
        },
        "response": []
    },
    {
        "name": "POST Send Multiple Push",
        "request": {
            "method": "POST",
            "header": [
                {"key": "Authorization", "value": "Bearer {{access_token}}"},
                {"key": "Content-Type", "value": "application/json"}
            ],
            "body": {
                "mode": "raw",
                "raw": "{\n    \"tokens\": [\"fcm_token_1\", \"fcm_token_2\"],\n    \"title\": \"Daily Announcement\",\n    \"body\": \"Deliveries start at 6:00 AM tomorrow.\",\n    \"data\": {}\n}"
            },
            "url": {
                "raw": "{{city_url}}/api/notifications/send-multiple/",
                "host": ["{{city_url}}"],
                "path": ["api", "notifications", "send-multiple", ""]
            }
        },
        "response": []
    },
    {
        "name": "POST Send Topic Push",
        "request": {
            "method": "POST",
            "header": [
                {"key": "Authorization", "value": "Bearer {{access_token}}"},
                {"key": "Content-Type", "value": "application/json"}
            ],
            "body": {
                "mode": "raw",
                "raw": "{\n    \"topic\": \"nagpur_drivers\",\n    \"title\": \"Route Ready\",\n    \"body\": \"Today routes have been generated.\",\n    \"data\": {}\n}"
            },
            "url": {
                "raw": "{{city_url}}/api/notifications/send-topic/",
                "host": ["{{city_url}}"],
                "path": ["api", "notifications", "send-topic", ""]
            }
        },
        "response": []
    }
]

for fp in target_files:
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Replace or add '14. Notifications'
        found = False
        for folder in data.get("item", []):
            if folder.get("name") == "14. Notifications":
                folder["item"] = notifications_items
                found = True
                break
        if not found:
            data.get("item", []).append({
                "name": "14. Notifications",
                "item": notifications_items
            })
            
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Updated 14. Notifications in {fp}")
