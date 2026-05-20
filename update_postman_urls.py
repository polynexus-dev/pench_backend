import json

postman_file = "documentation/postman_collection.json"

with open(postman_file, "r", encoding="utf-8") as f:
    data = json.load(f)

count = 0

def update_url(url_obj):
    global count
    updated = False
    if not url_obj:
        return False
    
    # 1. Update raw URL string
    raw = url_obj.get("raw", "")
    if "/api/erp/subs" in raw:
        url_obj["raw"] = raw.replace("/api/erp/subs", "/api/erp/subscriptions")
        updated = True
        
    # 2. Update path list
    path_list = url_obj.get("path", [])
    if isinstance(path_list, list) and "subs" in path_list:
        idx = path_list.index("subs")
        path_list[idx] = "subscriptions"
        url_obj["path"] = path_list
        updated = True
        
    if updated:
        count += 1
    return updated

def recurse_items(items):
    for item in items:
        if "item" in item:
            recurse_items(item["item"])
        else:
            req = item.get("request", {})
            update_url(req.get("url"))
            
            # Also update responses if any
            for resp in item.get("response", []):
                orig_req = resp.get("originalRequest", {})
                update_url(orig_req.get("url"))

recurse_items(data.get("item", []))

with open(postman_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4)

print(f"Successfully updated {count} URL paths in {postman_file}")
