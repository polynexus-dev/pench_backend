import json

def find_request(items, name):
    for item in items:
        if "item" in item:
            res = find_request(item["item"], name)
            if res:
                return res
        else:
            if item.get("name") == name:
                return item
    return None

with open("documentation/postman_collection.json", "r", encoding="utf-8") as f:
    d = json.load(f)

req = find_request(d.get("item", []), "POST Reconcile")
if req:
    print(json.dumps(req, indent=2))
else:
    print("Not found")
