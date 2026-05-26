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
            if (
                "subscription" in name.lower()
                or "subscription"
                in item.get("request", {}).get("url", {}).get("raw", "").lower()
            ):
                print(f"Request: {curr_path}")


recurse_items(data.get("item", []))
