import json

postman_file = "documentation/postman_collection.json"

with open(postman_file, "r", encoding="utf-8") as f:
    data = json.load(f)

def find_bulk_update_request(items):
    for item in items:
        if item.get("name") == "PATCH Bulk Update Subscriptions":
            return item
        if "item" in item:
            res = find_bulk_update_request(item["item"])
            if res:
                return res
    return None

req = find_bulk_update_request(data.get("item", []))
if req:
    print(json.dumps(req, indent=2))
else:
    print("Request not found")
