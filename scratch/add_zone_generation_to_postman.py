import json

postman_file = "documentation/postman_collection.json"

with open(postman_file, "r", encoding="utf-8") as f:
    collection = json.load(f)

new_request = {
    "name": "POST Generate Zones From Excel",
    "request": {
        "method": "POST",
        "header": [
            {
                "key": "Authorization",
                "value": "Bearer {{access_token}}"
            }
        ],
        "url": {
            "raw": "{{city_url}}/api/ems/zones/generate-from-excel/",
            "host": [
                "{{city_url}}"
            ],
            "path": [
                "api",
                "ems",
                "zones",
                "generate-from-excel",
                ""
            ]
        },
        "body": {
            "mode": "formdata",
            "formdata": [
                {
                    "key": "file",
                    "type": "file",
                    "description": (
                        "Excel (.xlsx) with customer name/phone/email/address/lat/lon columns "
                        "plus a driver/rider column. Generates one non-overlapping Voronoi zone "
                        "per driver from their customers' locations, clipped to the city boundary. "
                        "Existing customers (matched by phone/email) are left untouched; only new "
                        "ones are created. Safe to re-run — existing zones are updated in place "
                        "instead of duplicated. Requires the ERP_Admins group."
                    ),
                }
            ]
        }
    }
}

# Locate "02. Platform & Tenants" > "Zones (Zone)"
platform_folder = next(
    (f for f in collection["item"] if f.get("name", "").startswith("02.")), None
)
if not platform_folder:
    raise SystemExit("Could not find '02. Platform & Tenants' folder in the collection.")

zones_folder = next(
    (f for f in platform_folder.get("item", []) if f.get("name", "").startswith("Zones")), None
)
if not zones_folder:
    raise SystemExit("Could not find 'Zones (Zone)' folder under '02. Platform & Tenants'.")

existing_names = [r.get("name") for r in zones_folder.get("item", [])]
if new_request["name"] in existing_names:
    idx = existing_names.index(new_request["name"])
    zones_folder["item"][idx] = new_request
    print("Updated existing 'POST Generate Zones From Excel' request.")
else:
    # Insert right after "POST Create Zone" for logical grouping.
    create_idx = next(
        (i for i, r in enumerate(zones_folder["item"]) if r.get("name") == "POST Create Zone"),
        None,
    )
    insert_at = create_idx + 1 if create_idx is not None else len(zones_folder["item"])
    zones_folder["item"].insert(insert_at, new_request)
    print("Added 'POST Generate Zones From Excel' request to the Zones (Zone) folder.")

with open(postman_file, "w", encoding="utf-8") as f:
    json.dump(collection, f, indent=4)

print("Done! Postman collection saved successfully.")
