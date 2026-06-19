import json

endpoints = []
def list_endpoints(items, path=""):
    for item in items:
        name = item.get("name")
        curr_path = f"{path} / {name}" if path else name
        if "item" in item:
            list_endpoints(item["item"], curr_path)
        else:
            method = item.get("request", {}).get("method", "UNKNOWN")
            url = item.get("request", {}).get("url", {})
            if isinstance(url, dict):
                raw_url = url.get("raw", "")
            else:
                raw_url = str(url)
            endpoints.append(f"[{method}] {curr_path} -> {raw_url}")

with open("documentation/postman_collection.json", "r", encoding="utf-8") as f:
    data = json.load(f)

list_endpoints(data.get("item", []))

with open("scratch/endpoints.txt", "w", encoding="utf-8") as f:
    for ep in endpoints:
        f.write(ep + "\n")

print(f"Wrote {len(endpoints)} endpoints to scratch/endpoints.txt")
