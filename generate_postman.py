import json
import os

def generate_collection():
    collection_name = "Pench ERP - PERMANENT MASTER v4.2.1"
    
    def make_url(url_str):
        # Ensure trailing slash
        if "?" not in url_str and not url_str.endswith("/"):
            url_str += "/"
            
        # Extract host and path without resolving variables for the host array
        if url_str.startswith("{{base_url}}"):
            host = ["{{base_url}}"]
            path_part = url_str.replace("{{base_url}}/", "")
        elif url_str.startswith("{{city_url}}"):
            host = ["{{city_url}}"]
            path_part = url_str.replace("{{city_url}}/", "")
        else:
            parts = url_str.split("/")
            host = [parts[2]] if len(parts) > 2 else []
            path_part = "/".join(parts[3:]) if len(parts) > 3 else ""

        path = [p for p in path_part.split("/") if p]
        if url_str.endswith("/"):
            path.append("")
            
        return {
            "raw": url_str,
            "host": host,
            "path": path
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
        "info": {
            "name": collection_name, 
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        },
        "variable": [
            {"key": "base_url", "value": "https://pench.api.polynexus.in", "type": "string"},
            {"key": "city_url", "value": "https://nagpur.pench.api.polynexus.in", "type": "string"},
            {"key": "access_token", "value": "", "type": "string"},
            {"key": "route_id", "value": "1", "type": "string"},
            {"key": "order_id", "value": "1", "type": "string"},
            {"key": "last_id", "value": "1", "type": "string"}
        ],
        "item": [
            {
                "name": "00. SPECIAL: Driver Mobile App",
                "item": [
                    {"name": "POST Driver Check-in", "request": {"method": "POST", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "url": make_url("{{city_url}}/api/ems/drivers/check-in/"), "body": {"mode": "raw", "raw": "{}"}}},
                    {"name": "GET My Active Route", "request": {"method": "GET", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "url": make_url("{{city_url}}/api/erp/orders/driver/my-route/")}},
                    {"name": "POST Start Trip", "request": {"method": "POST", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "url": make_url("{{city_url}}/api/erp/orders/driver/{{route_id}}/start-trip/"), "body": {"mode": "raw", "raw": "{}"}}},
                    {"name": "POST Submit Delivery", "request": {"method": "POST", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "body": {"mode": "raw", "raw": "{\"bottles_returned\": 2}"}, "url": make_url("{{city_url}}/api/erp/orders/driver/{{order_id}}/submit-delivery/")}},
                    {"name": "POST Complete Trip", "request": {"method": "POST", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "url": make_url("{{city_url}}/api/erp/orders/driver/{{route_id}}/complete-trip/"), "body": {"mode": "raw", "raw": "{}"}}}
                ]
            },
            {
                "name": "01. Auth & Registration",
                "item": [
                    {"name": "POST Standard Login", "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": json.dumps({"username": "admin", "password": "password123"}, indent=4)}, "url": make_url("{{base_url}}/api/accounts/login/")}},
                    {"name": "GET Me (Profile)", "request": {"method": "GET", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "url": make_url("{{base_url}}/api/accounts/me/")}},
                    {"name": "POST Request OTP", "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": json.dumps({"phone": "918000000101"}, indent=4)}, "url": make_url("{{base_url}}/api/accounts/request-otp/")}},
                    {"name": "POST Login OTP", "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": json.dumps({"phone": "918000000101", "code": "123456"}, indent=4)}, "url": make_url("{{base_url}}/api/accounts/login-otp/")}},
                    {
                        "name": "User Registration (Templates)",
                        "item": [
                            {"name": "Register: SuperAdmin", "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": json.dumps({"username": "superadmin", "password": "password123", "email": "super@example.com", "phone": "9100000001", "first_name": "Super", "last_name": "Admin", "role": "SuperAdmin", "is_erp_user": True}, indent=4)}, "url": make_url("{{base_url}}/api/accounts/register/")}},
                            {"name": "Register: Staff", "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": json.dumps({"username": "staffuser", "password": "password123", "email": "staff@example.com", "phone": "9100000002", "first_name": "Staff", "last_name": "User", "role": "Staff", "is_erp_user": True}, indent=4)}, "url": make_url("{{base_url}}/api/accounts/register/")}},
                            {"name": "Register: Manager", "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": json.dumps({"username": "manageruser", "password": "password123", "email": "manager@example.com", "phone": "9100000003", "first_name": "Manager", "last_name": "User", "role": "Managers", "is_erp_user": True}, indent=4)}, "url": make_url("{{base_url}}/api/accounts/register/")}},
                            {"name": "Register: Driver", "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": json.dumps({"username": "driveruser", "password": "password123", "email": "driver@example.com", "phone": "9100000004", "first_name": "Driver", "last_name": "User", "role": "Drivers", "is_driver": True, "tenant_schema": "nagpur"}, indent=4)}, "url": make_url("{{base_url}}/api/accounts/register/")}},
                            {"name": "Register: Customer (Mandatory Fields)", "request": {"method": "POST", "header": [{"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": json.dumps({"username": "customeruser", "password": "password123", "email": "customer@example.com", "phone": "9100000005", "role": "Customers", "is_customer": True, "tenant_schema": "nagpur"}, indent=4)}, "url": make_url("{{base_url}}/api/accounts/register/")}},
                        ]
                    },
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
                    {"name": "PATCH Bulk Update Products", "request": {"method": "PATCH", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}, {"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": json.dumps([{"id": 1, "unit_price": "65.00"}], indent=4)}, "url": make_url("{{city_url}}/api/erp/inventory/products/bulk_update/")}},
                    
                    crud_folder("Warehouses", "city_url", "api/erp/inventory/warehouses", "Warehouse"),
                    
                    crud_folder("Stock Levels", "city_url", "api/erp/inventory/stock", "Stock", {"product": 1, "warehouse": 1, "quantity": 100}),
                    {"name": "PATCH Bulk Update Stock", "request": {"method": "PATCH", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}, {"key": "Content-Type", "value": "application/json"}], "body": {"mode": "raw", "raw": json.dumps([{"id": 1, "quantity": 120}], indent=4)}, "url": make_url("{{city_url}}/api/erp/inventory/stock/bulk_update/")}},
                    
                    crud_folder("Bottle Types", "city_url", "api/erp/inventory/bottle-types", "BottleType", {"name": "1L Glass Bottle", "deposit_amount": "50.00", "volume_ml": 1000}),
                    
                    crud_folder("Bottle Transactions", "city_url", "api/erp/inventory/bottle-transactions", "Transaction", {"bottle_type": 1, "customer": 1, "transaction_type": "issued", "quantity": 2}),
                    
                    {"name": "GET Customer Bottle Balances", "request": {"method": "GET", "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}], "url": make_url("{{city_url}}/api/erp/inventory/bottle-balances/")}}
                ]
            },
            {
                "name": "05. Logistics & Route Optimization",
                "item": [
                    crud_folder("Orders", "city_url", "api/erp/orders", "Order"),
                    crud_folder("Routes", "city_url", "api/erp/orders/routes", "Route"),
                    {"name": "POST Create Optimized Route", "request": {"method": "POST", "url": make_url("{{city_url}}/api/erp/orders/routes/create-optimized/"), "body": {"mode": "raw", "raw": "{}"}}}
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
                    {"name": "POST Vacation Mode", "request": {"method": "POST", "url": make_url("{{city_url}}/api/erp/subs/{{last_id}}/vacation/"), "body": {"mode": "raw", "raw": "{}"}}} ,
                    {"name": "POST Update Quantity", "request": {"method": "POST", "url": make_url("{{city_url}}/api/erp/subs/{{last_id}}/update-quantity/"), "body": {"mode": "raw", "raw": "{\"quantity\": 2}"}}}
                ]
            },
            {
                "name": "10. Taxation",
                "item": [
                    crud_folder("Tax Rules", "city_url", "api/erp/taxation/taxes", "Tax")
                ]
            }
        ],
        "event": [{ "listen": "test", "script": { "type": "text/javascript", "exec": [ "var jsonData = pm.response.json(); if (jsonData.access) { pm.environment.set('access_token', jsonData.access); } if (jsonData.id) { pm.environment.set('last_id', jsonData.id); }" ] } }]
    }
    
    with open("documentation/postman_collection.json", "w") as f:
        json.dump(collection, f, indent=4)
    print(f"Permanent Master Collection {collection_name} generated.")

if __name__ == "__main__":
    generate_collection()
