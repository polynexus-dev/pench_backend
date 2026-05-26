import json
import os

COLLECTION_PATH = "documentation/postman_collection.json"

with open(COLLECTION_PATH, "r") as f:
    collection = json.load(f)

# Find "02. Platform & Tenants" folder
target_folder = None
for item in collection.get("item", []):
    if item.get("name") == "02. Platform & Tenants":
        target_folder = item
        break

if target_folder:
    # Check if Companies already exists
    exists = any(
        i.get("name") == "Companies (Company)" for i in target_folder.get("item", [])
    )
    if not exists:
        companies_item = {
            "name": "Companies (Company)",
            "item": [
                {
                    "name": "GET List Companies",
                    "request": {
                        "method": "GET",
                        "header": [
                            {"key": "Authorization", "value": "Bearer {{access_token}}"}
                        ],
                        "url": {
                            "raw": "{{base_url}}/api/erp/tenants/companies/",
                            "host": ["{{base_url}}"],
                            "path": ["api", "erp", "tenants", "companies"],
                        },
                    },
                },
                {
                    "name": "POST Create Company",
                    "request": {
                        "method": "POST",
                        "header": [
                            {
                                "key": "Authorization",
                                "value": "Bearer {{access_token}}",
                            },
                            {"key": "Content-Type", "value": "application/json"},
                        ],
                        "body": {
                            "mode": "raw",
                            "raw": '{\n    "name": "Aniket Corp",\n    "code": "ANI"\n}',
                        },
                        "url": {
                            "raw": "{{base_url}}/api/erp/tenants/companies/",
                            "host": ["{{base_url}}"],
                            "path": ["api", "erp", "tenants", "companies"],
                        },
                    },
                },
            ],
        }
        target_folder["item"].insert(0, companies_item)

        with open(COLLECTION_PATH, "w") as f:
            json.dump(collection, f, indent=4)
        print("Successfully updated Postman collection with Companies endpoints.")
    else:
        print("Companies folder already exists in the collection.")
else:
    print("Could not find '02. Platform & Tenants' folder.")
