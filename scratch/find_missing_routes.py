import os
import sys
import json
import django

sys.path.insert(0, r"c:\Users\admin\Desktop\tejas\Pench\pench_backend")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.urls import get_resolver
from config.urls import urlpatterns as public_patterns
from config.urls_tenants import urlpatterns as tenant_patterns

collection_path = r"c:\Users\admin\Desktop\tejas\Pench\postman_collection (4).json"
with open(collection_path, "r", encoding="utf-8") as f:
    col = json.load(f)

# Extract raw URLs from postman
postman_paths = set()
def extract(items):
    for it in items:
        if "item" in it:
            extract(it["item"])
        else:
            req = it.get("request", {})
            raw = req.get("url", {}).get("raw", "") if isinstance(req.get("url"), dict) else str(req.get("url", ""))
            clean = raw.replace("{{base_url}}", "").replace("{{city_url}}", "")
            clean = clean.split("?")[0].strip("/")
            if clean:
                postman_paths.add(clean)

extract(col.get("item", []))

print(f"Total unique cleaned Postman paths: {len(postman_paths)}")

def get_routes(patterns, prefix=""):
    routes = []
    for p in patterns:
        if hasattr(p, "url_patterns"):
            routes.extend(get_routes(p.url_patterns, prefix + str(p.pattern)))
        else:
            full = (prefix + str(p.pattern)).strip("^$").strip("/")
            # ignore admin, schema-graph, etc.
            if not full.startswith("admin") and not full.startswith("schema"):
                routes.append(full)
    return routes

pub_routes = get_routes(public_patterns)
ten_routes = get_routes(tenant_patterns)

print(f"Public app routes: {len(pub_routes)}")
print(f"Tenant app routes: {len(ten_routes)}")

# Check missing major routes (e.g. notifications, etc.)
missing = []
for r in pub_routes + ten_routes:
    # simplify regex in route
    import re
    simple = re.sub(r'\([^)]+\)', 'ID', r)
    simple = re.sub(r'<[^>]+>', 'ID', simple).strip("/")
    # check if any postman path matches
    found = False
    for p in postman_paths:
        p_simple = re.sub(r'\{\{[^}]+\}\}', 'ID', p).strip("/")
        if simple == p_simple or simple in p_simple or p_simple in simple:
            found = True
            break
    if not found:
        missing.append((r, simple))

print(f"Routes in Django not in Postman: {len(missing)}")
for r, s in missing[:40]:
    print(f"  Missing: {s} (pattern: {r})")
