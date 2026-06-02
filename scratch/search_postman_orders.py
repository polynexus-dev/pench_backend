import json

with open("documentation/postman_collection.json", "r", encoding="utf-8") as f:
    data = json.load(f)


def print_urls(items, path=""):
    for item in items:
        name = item.get("name")
        curr_path = f"{path} / {name}" if path else name
        if "item" in item:
            print_urls(item["item"], curr_path)
        else:
            req = item.get("request", {})
            url = req.get("url", {})
            raw_url = url.get("raw", "") if isinstance(url, dict) else url
            method = req.get("method", "GET")
            if (
                "order" in name.lower()
                or "driver" in name.lower()
                or "route" in name.lower()
            ):
                print(f"[{method}] {curr_path} -> {raw_url}")


print_urls(data.get("item", []))
