import os
import sys
import json
import django

current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir.lower() not in [p.lower() for p in sys.path]:
    sys.path.insert(0, current_dir)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.urls import get_resolver
from django_tenants.utils import schema_context

collection_path = r"c:\Users\admin\Desktop\tejas\Pench\postman_collection (4).json"
with open(collection_path, "r", encoding="utf-8") as f:
    col = json.load(f)

# Extract all endpoints from collection
endpoints = []
def extract(items, path=""):
    for it in items:
        name = it.get("name", "")
        cur = f"{path} > {name}" if path else name
        if "item" in it:
            extract(it["item"], cur)
        else:
            req = it.get("request", {})
            method = req.get("method", "GET")
            raw_url = req.get("url", {}).get("raw", "") if isinstance(req.get("url"), dict) else str(req.get("url", ""))
            endpoints.append((cur, method, raw_url))

extract(col.get("item", []))

print(f"Extracted {len(endpoints)} endpoints from Postman collection.")

# Get public schema URL patterns
from config.urls import urlpatterns as public_patterns
# Get tenant schema URL patterns
from config.urls_tenants import urlpatterns as tenant_patterns

def get_urls(patterns, prefix=""):
    result = []
    for p in patterns:
        if hasattr(p, "url_patterns"):
            result.extend(get_urls(p.url_patterns, prefix + str(p.pattern)))
        else:
            result.append(prefix + str(p.pattern))
    return result

public_urls = get_urls(public_patterns)
tenant_urls = get_urls(tenant_patterns)

print(f"Total public URL patterns: {len(public_urls)}")
print(f"Total tenant URL patterns: {len(tenant_urls)}")

# Check collection endpoints against patterns
# Replace variables in raw_url:
# {{base_url}} -> public
# {{city_url}} -> tenant

print("\n--- Checking endpoints for potential 404s or misroutings ---")
not_matched = []

import re

from django.urls import resolve, Resolver404

for cur, method, url in endpoints:
    # normalize url
    clean = url.replace("{{base_url}}", "").replace("{{city_url}}", "")
    clean = clean.split("?")[0]
    if not clean.startswith("/"):
        clean = "/" + clean
    if not clean.endswith("/"):
        clean += "/"
        
    # replace variables like {{last_id}}, {{route_id}}, {{order_id}}, {{qr_id}} with sample values
    clean = re.sub(r'\{\{[a-zA-Z0-9_-]+\}\}', '1', clean)
    
    is_base = "{{base_url}}" in url
    is_city = "{{city_url}}" in url
    
    matched = False
    expected_urlconf = "config.urls" if is_base else "config.urls_tenants"
    alt_urlconf = "config.urls_tenants" if is_base else "config.urls"
    
    try:
        match = resolve(clean, urlconf=expected_urlconf)
        matched = True
    except Resolver404:
        try:
            match = resolve(clean, urlconf=alt_urlconf)
            not_matched.append((cur, method, url, clean, True, "tenant" if is_base else "public"))
        except Resolver404:
            not_matched.append((cur, method, url, clean, False, "none"))

print(f"Unmatched endpoints: {len(not_matched)}")
for cur, method, url, check, other, target in not_matched:
    if other:
        print(f"[WRONG HOST] {cur} ({method} {url}) -> routes to {target} schema!")
    else:
        print(f"[NOT FOUND (404)] {cur} ({method} {url}) [path: {check}]")

