import json

postman_file = "documentation/postman_collection.json"

with open(postman_file, "r", encoding="utf-8") as f:
    data = json.load(f)

# Find folder '09. Subscriptions'
sub_folder = None
for item in data.get("item", []):
    if item.get("name") == "09. Subscriptions":
        sub_folder = item
        break

if not sub_folder:
    print("09. Subscriptions folder not found")
    exit(1)

# Find nested folder 'Subscriptions (Subscription)'
nested_folder = None
for item in sub_folder.get("item", []):
    if item.get("name") == "Subscriptions (Subscription)":
        nested_folder = item
        break

if not nested_folder:
    print("Subscriptions (Subscription) folder not found")
    exit(1)

# 1. Remove GET Subscription Frequencies if it exists
original_len = len(nested_folder.get("item", []))
nested_folder["item"] = [
    r for r in nested_folder.get("item", [])
    if r.get("name") != "GET Subscription Frequencies"
]
if len(nested_folder["item"]) < original_len:
    print("Removed 'GET Subscription Frequencies' from the collection.")

# 2. Add GET Subscription Grouped Summary if it doesn't exist
exists = False
for r in nested_folder.get("item", []):
    if r.get("name") == "GET Subscription Grouped Summary":
        exists = True
        break

if not exists:
    new_request = {
        "name": "GET Subscription Grouped Summary",
        "request": {
            "method": "GET",
            "header": [
                {
                    "key": "Authorization",
                    "value": "Bearer {{access_token}}"
                }
            ],
            "url": {
                "raw": "{{city_url}}/api/erp/subscriptions/grouped-summary/",
                "host": [
                    "{{city_url}}"
                ],
                "path": [
                    "api",
                    "erp",
                    "subscriptions",
                    "grouped-summary",
                    ""
                ]
            }
        },
        "response": []
    }
    nested_folder["item"].append(new_request)
    print("Added 'GET Subscription Grouped Summary' to the collection.")
else:
    print("'GET Subscription Grouped Summary' already exists.")

# Save file
with open(postman_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4, ensure_ascii=False)

print("Postman collection updated successfully.")
