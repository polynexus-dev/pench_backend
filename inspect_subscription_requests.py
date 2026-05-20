import json

with open("documentation/postman_collection.json", "r", encoding="utf-8") as f:
    data = json.load(f)

subscription_requests = []

def recurse_items(items, path=""):
    for item in items:
        name = item.get("name")
        curr_path = f"{path} / {name}" if path else name
        if "item" in item:
            recurse_items(item["item"], curr_path)
        else:
            if "subscription" in name.lower() or "subscription" in item.get("request", {}).get("url", {}).get("raw", "").lower():
                subscription_requests.append({
                    "path": curr_path,
                    "url": item.get("request", {}).get("url", {}).get("raw", ""),
                    "method": item.get("request", {}).get("method", ""),
                    "body": item.get("request", {}).get("body", {}).get("raw", "")
                })

recurse_items(data.get("item", []))

with open("subscription_inspect.json", "w", encoding="utf-8") as f:
    json.dump(subscription_requests, f, indent=4)

print("Inspection file written to subscription_inspect.json")
