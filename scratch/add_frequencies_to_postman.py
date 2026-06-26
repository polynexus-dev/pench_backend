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

# Construct the new request object
new_request = {
    "name": "GET Subscription Frequencies",
    "request": {
        "method": "GET",
        "header": [
            {
                "key": "Authorization",
                "value": "Bearer {{access_token}}"
            }
        ],
        "url": {
            "raw": "{{city_url}}/api/erp/subscriptions/frequencies/",
            "host": [
                "{{city_url}}"
            ],
            "path": [
                "api",
                "erp",
                "subscriptions",
                "frequencies",
                ""
            ]
        }
    },
    "response": []
}

# Check if it already exists to avoid duplicates
exists = False
for r in nested_folder.get("item", []):
    if r.get("name") == "GET Subscription Frequencies":
        exists = True
        break

if not exists:
    nested_folder["item"].append(new_request)
    with open(postman_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print("Successfully added 'GET Subscription Frequencies' to Postman collection.")
else:
    print("'GET Subscription Frequencies' already exists in the collection.")
