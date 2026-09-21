import json
import re

collection_path = r"c:\Users\admin\Desktop\tejas\Pench\postman_collection (4).json"
with open(collection_path, "r", encoding="utf-8") as f:
    col = json.load(f)

print("Inspecting collection...")

mismatches = []
json_syntax_errors = []
url_issues = []
all_requests = []

def walk(items, path=""):
    for item in items:
        name = item.get("name", "")
        cur = f"{path} > {name}" if path else name
        if "item" in item:
            walk(item["item"], cur)
        else:
            all_requests.append((cur, item))
            req = item.get("request", {})
            method = req.get("method", "")
            url = req.get("url", {})
            raw_url = url.get("raw", "") if isinstance(url, dict) else str(url)
            
            # Check url structure
            if isinstance(url, dict):
                path_parts = url.get("path", [])
                host_parts = url.get("host", [])
                if not raw_url:
                    url_issues.append((cur, "Empty raw url"))
            
            body = req.get("body", {})
            if body.get("mode") == "raw":
                raw_body = body.get("raw", "")
                # check response examples
                for resp in item.get("response", []):
                    orig_body = resp.get("originalRequest", {}).get("body", {}).get("raw", "")
                    if orig_body and raw_body and orig_body != raw_body:
                        # if orig_body is a stringified JSON like "\"{\\n...}\""
                        if orig_body.startswith('"') and orig_body.endswith('"'):
                            try:
                                unescaped = json.loads(orig_body)
                                if unescaped != raw_body:
                                    mismatches.append((cur, raw_body, unescaped))
                            except Exception:
                                pass

walk(col.get("item", []))

print(f"Total requests: {len(all_requests)}")
print(f"Total mismatches between request and example request body: {len(mismatches)}")
for cur, req_b, orig_b in mismatches:
    print(f"\n--- {cur} ---")
    print("Request Body:\n", req_b[:150])
    print("Original in Example:\n", orig_b[:150])
