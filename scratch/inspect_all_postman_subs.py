import json

postman_file = "documentation/postman_collection.json"

with open(postman_file, "r", encoding="utf-8") as f:
    data = json.load(f)

def print_subs(items, path=""):
    for item in items:
        name = item.get("name")
        curr_path = f"{path} / {name}" if path else name
        if "item" in item:
            print_subs(item["item"], curr_path)
        else:
            if "subscription" in name.lower() or "subscription" in item.get("request", {}).get("url", {}).get("raw", "").lower():
                print(f"\n======================================")
                print(f"Path: {curr_path}")
                print(f"Method: {item.get('request', {}).get('method')}")
                print(f"URL: {item.get('request', {}).get('url', {}).get('raw')}")
                body = item.get('request', {}).get('body', {})
                print(f"Body Mode: {body.get('mode')}")
                print(f"Body Raw:\n{body.get('raw')}")

print_subs(data.get("item", []))
