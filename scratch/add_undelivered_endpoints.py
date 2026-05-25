import json

print("=== INJECTING UNDELIVERED ENDPOINTS INTO POSTMAN COLLECTION ===")

with open("documentation/postman_collection.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# 1. Find '00. SPECIAL: Driver Mobile App' folder
driver_folder = None
for folder in data.get("item", []):
    if folder.get("name") == "00. SPECIAL: Driver Mobile App":
        driver_folder = folder
        break

# 2. Find '05. Logistics & Route Optimization' -> 'Orders (Order)' folder
logistics_folder = None
orders_folder = None
for folder in data.get("item", []):
    if folder.get("name") == "05. Logistics & Route Optimization":
        logistics_folder = folder
        break

if logistics_folder:
    for sub in logistics_folder.get("item", []):
        if sub.get("name") == "Orders (Order)":
            orders_folder = sub
            break

submit_undelivered_request = {
  "name": "POST Submit Undelivered",
  "request": {
    "method": "POST",
    "header": [
      {
        "key": "Authorization",
        "value": "Bearer {{access_token}}"
      }
    ],
    "body": {
      "mode": "formdata",
      "formdata": [
        {
          "key": "pod_image",
          "type": "file",
          "src": []
        },
        {
          "key": "pod_latitude",
          "value": "21.1458",
          "type": "text"
        },
        {
          "key": "pod_longitude",
          "value": "79.0882",
          "type": "text"
        }
      ]
    },
    "url": {
      "raw": "{{city_url}}/api/erp/orders/driver/{{last_id}}/submit-undelivered/",
      "host": [
        "{{city_url}}"
      ],
      "path": [
        "api",
        "erp",
        "orders",
        "driver",
        "{{last_id}}",
        "submit-undelivered"
      ]
    }
  },
  "response": []
}

mark_undelivered_request = {
  "name": "POST Mark Undelivered",
  "request": {
    "method": "POST",
    "header": [
      {
        "key": "Authorization",
        "value": "Bearer {{access_token}}"
      }
    ],
    "body": {
      "mode": "formdata",
      "formdata": [
        {
          "key": "pod_image",
          "type": "file",
          "src": []
        }
      ]
    },
    "url": {
      "raw": "{{city_url}}/api/erp/orders/{{last_id}}/mark-undelivered/",
      "host": [
        "{{city_url}}"
      ],
      "path": [
        "api",
        "erp",
        "orders",
        "{{last_id}}",
        "mark-undelivered"
      ]
    }
  },
  "response": []
}

injected_driver = False
injected_orders = False

if driver_folder:
    driver_folder.setdefault("item", []).append(submit_undelivered_request)
    print("[SUCCESS] Injected 'POST Submit Undelivered' to '00. SPECIAL: Driver Mobile App'")
    injected_driver = True
else:
    print("[ERROR] Driver Mobile App folder not found!")

if orders_folder:
    orders_folder.setdefault("item", []).append(mark_undelivered_request)
    print("[SUCCESS] Injected 'POST Mark Undelivered' to '05. Logistics & Route Optimization / Orders (Order)'")
    injected_orders = True
else:
    print("[ERROR] Orders (Order) folder not found!")

if injected_driver or injected_orders:
    with open("documentation/postman_collection.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("[SUCCESS] Postman collection updated and saved successfully!")
else:
    print("[ERROR] No updates were written.")
