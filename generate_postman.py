import json
import os

def generate_collection():
    collection_name = "Pench ERP - PERMANENT MASTER v4.1.0"
    
    def make_url(url_str):
        parts = url_str.replace("{{base_url}}", "https://pench.api.polynexus.in").replace("{{city_url}}", "https://nagpur.pench.api.polynexus.in").split("/")
        return {
            "raw": url_str,
            "host": [parts[2]],
            "path": [p for p in parts[3:] if p]
        }

    def crud_folder(name, base_url_var, api_path, model_name, sample_body=None):
        return {
            "name": f"{name} ({model_name})",
            "item": [
                {"name": f"GET List {model_name}s", "request": {"method": "GET", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "url": make_url(f"{{{{{base_url_var}}}}}/{api_path}/")}},
                {"name": f"POST Create {model_name}", "request": {"method": "POST", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}, {"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": json.dumps(sample_body or {}, indent=4)}, "url": make_url(f"{{{{{base_url_var}}}}}/{api_path}/")}},
                {"name": f"GET Single {model_name}", "request": {"method": "GET", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "url": make_url(f"{{{{{base_url_var}}}}}/{api_path}/{{{{last_id}}}}/")}},
                {"name": f"PATCH Update {model_name}", "request": {"method": "PATCH", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}, {"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": json.dumps(sample_body or {}, indent=4)}, "url": make_url(f"{{{{{base_url_var}}}}}/{api_path}/{{{{last_id}}}}/")}},
                {"name": f"DELETE {model_name}", "request": {"method": "DELETE", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "url": make_url(f"{{{{{base_url_var}}}}}/{api_path}/{{{{last_id}}}}/")}}
            ]
        }

    collection = {
        "info": {"name": collection_name, "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "item": [
            {
                "name": "00. SPECIAL: Driver Mobile App",
                "item": [
                    {"name": "POST Driver Check-in", "request": {"method": "POST", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "url": make_url("{{city_url}}/api/ems/drivers/check-in/")}},
                    {"name": "GET My Active Route", "request": {"method": "GET", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "url": make_url("{{city_url}}/api/erp/orders/driver/my-route/")}},
                    {"name": "POST Start Trip", "request": {"method": "POST", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "url": make_url("{{city_url}}/api/erp/orders/driver/{{route_id}}/start-trip/")}},
                    {"name": "POST Submit Delivery", "request": {"method": "POST", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "body": {"mode": "raw", "raw": "{\"bottles_returned\": 2}"}, "url": make_url("{{city_url}}/api/erp/orders/driver/{{order_id}}/submit-delivery/")}},
                    {"name": "POST Complete Trip", "request": {"method": "POST", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "url": make_url("{{city_url}}/api/erp/orders/driver/{{route_id}}/complete-trip/")}}
                ]
            },
            {
                "name": "01. Auth & Accounts",
                "item": [
                    {"name": "POST Standard Login", "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": "{\"username\": \"admin\", \"password\": \"password123\"}"}, "url": make_url("{{base_url}}/api/accounts/login/")}},
                    {"name": "POST Request OTP", "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": "{\"phone\": \"918000000101\"}"}, "url": make_url("{{base_url}}/api/accounts/request-otp/")}},
                    {"name": "POST Login OTP", "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": "{\"phone\": \"918000000101\", \"code\": \"123456\"}"}, "url": make_url("{{base_url}}/api/accounts/login-otp/")}},
                    crud_folder("Global Users", "base_url", "api/accounts/users", "User")
                ]
            },
            {
                "name": "02. Platform & Tenants",
                "item": [
                    crud_folder("Cities", "base_url", "api/erp/tenants/cities", "City", {"name": "Nagpur", "schema_name": "nagpur"}),
                    crud_folder("Domains", "base_url", "api/erp/tenants/domains", "Domain")
                ]
            },
            {
                "name": "03. CRM & Customers",
                "item": [
                    crud_folder("Customers", "city_url", "api/erp/customers", "Customer", {"name": "John Doe", "phone": "9100000000"}),
                    {"name": "GET Customer QR Code", "request": {"method": "GET", "url": make_url("{{city_url}}/api/erp/customers/{{last_id}}/qr/")}}
                ]
            },
            {
                "name": "04. Inventory & Warehousing",
                "item": [
                    crud_folder("Products", "city_url", "api/erp/inventory/products", "Product", {"name": "Milk 1L", "sku": "M1", "unit_price": "60.00"}),
                    crud_folder("Warehouses", "city_url", "api/erp/inventory/warehouses", "Warehouse"),
                    {"name": "GET Stock Levels", "request": {"method": "GET", "url": make_url("{{city_url}}/api/erp/inventory/stocks/")}}
                ]
            },
            {
                "name": "05. Logistics & Route Optimization",
                "item": [
                    crud_folder("Orders", "city_url", "api/erp/orders", "Order"),
                    crud_folder("Routes", "city_url", "api/erp/orders/routes", "Route"),
                    {"name": "POST Create Optimized Route", "request": {"method": "POST", "url": make_url("{{city_url}}/api/erp/orders/routes/create-optimized/")}}
                ]
            },
            {
                "name": "06. Fleet & Driver Management",
                "item": [
                    crud_folder("City Drivers", "city_url", "api/ems/drivers", "Driver"),
                    {"name": "GET Track Driver Live", "request": {"method": "GET", "url": make_url("{{city_url}}/api/ems/tracking/")}}
                ]
            },
            {
                "name": "07. HR & Attendance",
                "item": [
                    crud_folder("Employees", "city_url", "api/erp/hr/employees", "Employee"),
                    crud_folder("Attendance", "city_url", "api/erp/hr/attendance", "Attendance")
                ]
            },
            {
                "name": "08. Finance & Billing",
                "item": [
                    crud_folder("Invoices", "city_url", "api/erp/finance/invoices", "Invoice"),
                    crud_folder("Payments", "city_url", "api/erp/finance/payments", "Payment")
                ]
            },
            {
                "name": "09. Subscriptions",
                "item": [
                    crud_folder("Subscriptions", "city_url", "api/erp/subs", "Subscription", {"customer": "CUSTOMER_UUID", "frequency": "daily"}),
                    {"name": "POST Vacation Mode", "request": {"method": "POST", "url": make_url("{{city_url}}/api/erp/subs/{{last_id}}/vacation/")}} ,
                    {"name": "POST Update Quantity", "request": {"method": "POST", "url": make_url("{{city_url}}/api/erp/subs/{{last_id}}/update-quantity/")}}
                ]
            },
            {
                "name": "10. Taxation",
                "item": [
                    crud_folder("Tax Rules", "city_url", "api/erp/taxation/taxes", "Tax")
                ]
            }
        ],
        "event": [{ "listen": "test", "script": { "type": "text/javascript", "exec": [ "var jsonData = pm.response.json(); if (jsonData.access) { pm.environment.set('access_token', jsonData.access); } if (jsonData.id) { pm.environment.set('last_id', jsonData.id); }" ] } }],
        "variable": [
            {"key": "base_url", "value": "https://pench.api.polynexus.in"},
            {"key": "city_url", "value": "https://nagpur.pench.api.polynexus.in"},
            {"key": "access_token", "value": ""},
            {"key": "route_id", "value": "1"},
            {"key": "order_id", "value": "1"},
            {"key": "last_id", "value": "1"}
        ]
    }
    
    with open("documentation/postman_collection.json", "w") as f:
        json.dump(collection, f, indent=4)
    print("Permanent Master Collection v4.1.0 generated.")

if __name__ == "__main__":
    generate_collection()
