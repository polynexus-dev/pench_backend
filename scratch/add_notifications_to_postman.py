import json
import os

postman_file = "documentation/postman_collection.json"

# Read existing collection
with open(postman_file, "r", encoding="utf-8") as f:
    collection = json.load(f)

# Define notifications folder structure
notifications_folder = {
    "name": "14. Notifications",
    "item": [
        {
            "name": "POST Save FCM Token",
            "request": {
                "method": "POST",
                "header": [
                    {
                        "key": "Authorization",
                        "value": "Bearer {{access_token}}"
                    },
                    {
                        "key": "Content-Type",
                        "value": "application/json"
                    }
                ],
                "body": {
                    "mode": "raw",
                    "raw": "{\n    \"token\": \"fcm_device_token_goes_here\"\n}"
                },
                "url": {
                    "raw": "{{city_url}}/api/notifications/save-token/",
                    "host": [
                        "{{city_url}}"
                    ],
                    "path": [
                        "api",
                        "notifications",
                        "save-token",
                        ""
                    ]
                }
            }
        },
        {
            "name": "GET List FCM Tokens",
            "request": {
                "method": "GET",
                "header": [
                    {
                        "key": "Authorization",
                        "value": "Bearer {{access_token}}"
                    }
                ],
                "url": {
                    "raw": "{{city_url}}/api/notifications/tokens/",
                    "host": [
                        "{{city_url}}"
                    ],
                    "path": [
                        "api",
                        "notifications",
                        "tokens",
                        ""
                    ]
                }
            }
        },
        {
            "name": "GET List In-App Notifications",
            "request": {
                "method": "GET",
                "header": [
                    {
                        "key": "Authorization",
                        "value": "Bearer {{access_token}}"
                    }
                ],
                "url": {
                    "raw": "{{city_url}}/api/notifications/",
                    "host": [
                        "{{city_url}}"
                    ],
                    "path": [
                        "api",
                        "notifications",
                        ""
                    ]
                }
            }
        },
        {
            "name": "PATCH Mark Notification as Read",
            "request": {
                "method": "PATCH",
                "header": [
                    {
                        "key": "Authorization",
                        "value": "Bearer {{access_token}}"
                    }
                ],
                "url": {
                    "raw": "{{city_url}}/api/notifications/{{notification_id}}/read/",
                    "host": [
                        "{{city_url}}"
                    ],
                    "path": [
                        "api",
                        "notifications",
                        "{{notification_id}}",
                        "read",
                        ""
                    ]
                }
            }
        },
        {
            "name": "PATCH Mark All Notifications as Read",
            "request": {
                "method": "PATCH",
                "header": [
                    {
                        "key": "Authorization",
                        "value": "Bearer {{access_token}}"
                    }
                ],
                "url": {
                    "raw": "{{city_url}}/api/notifications/read-all/",
                    "host": [
                        "{{city_url}}"
                    ],
                    "path": [
                        "api",
                        "notifications",
                        "read-all",
                        ""
                    ]
                }
            }
        },
        {
            "name": "POST Send Single Push (Test)",
            "request": {
                "method": "POST",
                "header": [
                    {
                        "key": "Content-Type",
                        "value": "application/json"
                    }
                ],
                "body": {
                    "mode": "raw",
                    "raw": "{\n    \"token\": \"fcm_device_token_goes_here\",\n    \"title\": \"Hello!\",\n    \"body\": \"This is a single push notification test.\",\n    \"data\": {\n        \"key\": \"value\"\n    }\n}"
                },
                "url": {
                    "raw": "{{city_url}}/api/notifications/send-single/",
                    "host": [
                        "{{city_url}}"
                    ],
                    "path": [
                        "api",
                        "notifications",
                        "send-single",
                        ""
                    ]
                }
            }
        },
        {
            "name": "POST Send Multicast Push (Test)",
            "request": {
                "method": "POST",
                "header": [
                    {
                        "key": "Content-Type",
                        "value": "application/json"
                    }
                ],
                "body": {
                    "mode": "raw",
                    "raw": "{\n    \"tokens\": [\n        \"fcm_device_token_1\"\n    ],\n    \"title\": \"Hello All!\",\n    \"body\": \"This is a multicast push notification test.\",\n    \"data\": {\n        \"key\": \"value\"\n    }\n}"
                },
                "url": {
                    "raw": "{{city_url}}/api/notifications/send-multiple/",
                    "host": [
                        "{{city_url}}"
                    ],
                    "path": [
                        "api",
                        "notifications",
                        "send-multiple",
                        ""
                    ]
                }
            }
        },
        {
            "name": "POST Send Topic Push (Test)",
            "request": {
                "method": "POST",
                "header": [
                    {
                        "key": "Content-Type",
                        "value": "application/json"
                    }
                ],
                "body": {
                    "mode": "raw",
                    "raw": "{\n    \"topic\": \"all_users\",\n    \"title\": \"Hello Topic Subscribers!\",\n    \"body\": \"This is a topic push notification test.\",\n    \"data\": {\n        \"key\": \"value\"\n    }\n}"
                },
                "url": {
                    "raw": "{{city_url}}/api/notifications/send-topic/",
                    "host": [
                        "{{city_url}}"
                    ],
                    "path": [
                        "api",
                        "notifications",
                        "send-topic",
                        ""
                    ]
                }
            }
        }
    ]
}

# Check if folder already exists and update or append it
existing_items = collection.get("item", [])
found_index = -1
for idx, folder in enumerate(existing_items):
    if folder.get("name") == "14. Notifications" or folder.get("name").endswith("Notifications"):
        found_index = idx
        break

if found_index != -1:
    existing_items[found_index] = notifications_folder
    print("Updated existing Notifications folder in Postman collection.")
else:
    existing_items.append(notifications_folder)
    print("Appended new Notifications folder to Postman collection.")

collection["item"] = existing_items

# Write updated collection
with open(postman_file, "w", encoding="utf-8") as f:
    json.dump(collection, f, indent=4)

print("Done! Postman collection saved successfully.")
