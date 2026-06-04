import json

with open("documentation/postman_collection.json", "r", encoding="utf-8") as f:
    data = json.load(f)

def recurse_items(items, path=""):
    for item in items:
        name = item.get("name")
        curr_path = f"{path} / {name}" if path else name
        if "item" in item:
            recurse_items(item["item"], curr_path)
        else:
            url_raw = item.get("request", {}).get("url", {}).get("raw", "")
            if "order" in name.lower() or "order" in url_raw.lower():
                print(f"Request: {curr_path} -> {item['request']['method']} {url_raw}")

recurse_items(data.get("item", []))
