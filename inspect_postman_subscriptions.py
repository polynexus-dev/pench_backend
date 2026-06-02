import json

postman_file = "documentation/postman_collection.json"

with open(postman_file, "r", encoding="utf-8") as f:
    data = json.load(f)


def print_tree(items, indent=""):
    for item in items:
        name = item.get("name", "")
        if "item" in item:
            print(f"{indent}[Folder] {name}")
            print_tree(item["item"], indent + "  ")
        else:
            req = item.get("request", {})
            method = req.get("method", "")
            url = (
                req.get("url", {}).get("raw", "")
                if isinstance(req.get("url"), dict)
                else req.get("url", "")
            )
            print(f"{indent}[Request] {method} {name} -> {url}")


print_tree(data.get("item", []))
