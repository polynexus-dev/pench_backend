import json

postman_file = "documentation/postman_collection.json"

with open(postman_file, "r", encoding="utf-8") as f:
    data = json.load(f)

def print_detailed_structure(item, depth=0):
    indent = "  " * depth
    name = item.get("name", "")
    if "item" in item:
        print(f"{indent}[Folder] {name}")
        for sub_item in item["item"]:
            print_detailed_structure(sub_item, depth + 1)
    else:
        req = item.get("request", {})
        method = req.get("method", "")
        url = req.get("url", {}).get("raw", "") if isinstance(req.get("url"), dict) else req.get("url", "")
        print(f"{indent}[Request] {method} {name} -> {url}")

def find_subscription_folder(items):
    for item in items:
        if item.get("name") == "09. Subscriptions":
            return item
        if "item" in item:
            res = find_subscription_folder(item["item"])
            if res:
                return res
    return None

folder = find_subscription_folder(data.get("item", []))
if folder:
    print_detailed_structure(folder)
else:
    print("Folder not found")
