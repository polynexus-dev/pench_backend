import json

postman_file = "documentation/postman_collection.json"

with open(postman_file, "r", encoding="utf-8") as f:
    data = json.load(f)

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
    print("Found folder:", folder.get("name"))
    print("Keys in folder:", folder.keys())
    print("Number of items in folder:", len(folder.get("item", [])))
    
    # Print the structure of the first request to understand format
    for item in folder.get("item", []):
        if "request" in item:
            print("\nRequest details for:", item["name"])
            print(json.dumps(item, indent=2))
            break
        elif "item" in item:
            # Check nested folders
            print("\nNested folder:", item["name"])
            for nested in item["item"]:
                if "request" in nested:
                    print("Nested Request details for:", nested["name"])
                    print(json.dumps(nested, indent=2))
                    break
            break
else:
    print("Subscription folder not found")
