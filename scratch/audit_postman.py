import json
import re

col_path = r"c:\Users\admin\Desktop\tejas\Pench\postman_collection (4).json"
with open(col_path, "r", encoding="utf-8") as f:
    col = json.load(f)

issues = []

def check(items, path=""):
    for item in items:
        name = item.get("name", "")
        cur = f"{path} > {name}" if path else name
        if "item" in item:
            check(item["item"], cur)
        else:
            req = item.get("request", {})
            method = req.get("method", "GET")
            url = req.get("url", {})
            raw_url = url.get("raw", "") if isinstance(url, dict) else str(url)
            
            # 1. Double slashes (except in protocol ://)
            check_url = raw_url.replace("://", "")
            if "//" in check_url:
                issues.append((cur, f"Double slash in URL: {raw_url}"))
                
            # 2. Check JSON raw body syntax
            body = req.get("body", {})
            if body.get("mode") == "raw":
                raw_body = body.get("raw", "")
                if raw_body.strip().startswith("{") or raw_body.strip().startswith("["):
                    # Replace Postman templates {{...}} with placeholder
                    dummy = re.sub(r'\{\{[a-zA-Z0-9_-]+\}\}', '"placeholder"', raw_body)
                    # Also replace unquoted boolean/integer template placeholders if any
                    dummy = re.sub(r':\s*"placeholder"', ': "placeholder"', dummy)
                    try:
                        json.loads(dummy)
                    except Exception as e:
                        issues.append((cur, f"JSON parse error in request body: {e} | Body: {raw_body[:80]}"))
                        
            # 3. Check for driver_name in non-driver requests
            if "driver_name" in req.get("body", {}).get("raw", "") and "driver" not in cur.lower():
                issues.append((cur, "Driver payload accidentally pasted in non-driver request!"))

check(col.get("item", []))

print(f"Total issues found: {len(issues)}")
for cur, err in issues:
    print(f"  [{cur}]: {err}")
