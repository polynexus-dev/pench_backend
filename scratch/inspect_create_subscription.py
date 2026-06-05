import json

postman_file = "documentation/postman_collection.json"

with open(postman_file, "r", encoding="utf-8") as f:
    data = json.load(f)

def find_create_subscription_request(items):
    for item in items:
        if item.get("name") == "POST Create Subscription":
            return item
        if "item" in item:
            res = find_create_subscription_request(item["item"])
            if res:
                return res
    return None

req = find_create_subscription_request(data.get("item", []))
if req:
    print(json.dumps(req, indent=2))
else:
    print("Request not found")
