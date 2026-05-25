import json

with open("documentation/postman_collection.json", "r", encoding="utf-8") as f:
    data = json.load(f)

def print_structure(items, indent=0):
    for item in items:
        name = item.get("name")
        if "item" in item:
            print("  " * indent + f"[Folder] {name}")
            print_structure(item["item"], indent + 1)
        else:
            print("  " * indent + f"[Request] {name} ({item.get('request', {}).get('method', 'GET')})")

print_structure(data.get("item", []))
