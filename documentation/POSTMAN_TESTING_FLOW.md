# 🧪 Pench ERP: End-to-End Postman Testing Flow

This document details the exact sequence for testing all features of the **Pench Logistics ERP** system using Postman. It is structured chronologically, matching a real-world business cycle—from setting up a new city-tenant down to daily route reconciliation and billing.

---

## ⚙️ Phase 1: Environment Setup in Postman

Before running requests, create a Postman Environment (e.g., **Pench Local**) with the following variables:

| Variable | Local Value | Description |
| :--- | :--- | :--- |
| `base_url` | `http://localhost:8000` (or `http://localhost:8083`) | Use the ASGI port for WebSocket / Daphne server. |
| `access_token` | *(Auto-set after login)* | Bearer authentication token. |
| `refresh_token`| *(Auto-set after login)* | Token used to renew session. |
| `company_id` | *(Set after creating Company)* | UUID of the corporate entity. |
| `city_id` | *(Set after creating City)* | UUID of the tenant City. |
| `zone_id` | *(Set after creating Zone)* | UUID of the delivery zone. |
| `product_id` | *(Set after creating Product)* | UUID of the milk/dairy product. |
| `warehouse_id`| *(Set after creating Warehouse)* | UUID of the storage depot. |
| `driver_user_id`| *(Set after registering Driver User)*| UUID of the Driver User account. |
| `driver_profile_id`| *(Set after creating Driver Profile)*| UUID of the Driver details profile. |
| `customer_user_id`| *(Set after registering Customer)*| UUID of the Customer User account. |
| `customer_profile_id`| *(Set after creating Customer Profile)*| UUID of the Customer details profile. |
| `subscription_id`| *(Set after creating Subscription)* | UUID of the active subscription. |
| `route_id` | *(Set after creating Route)* | UUID of the daily delivery route. |
| `order_id` | *(Set after generating orders)* | UUID of the specific daily order. |

---

## 🏙️ Phase 2: Platform & Tenant Setup (Public Schema)
*Execute these endpoints while connected to the global `base_url` using a SuperAdmin login.*

### 1. Register & Login as SuperAdmin
- **Request**: `01. Auth & Registration / User Registration (Templates) / Register: SuperAdmin`
  - **Method**: `POST`
  - **Action**: Creates a superuser account globally.
- **Request**: `01. Auth & Registration / POST Standard Login`
  - **Method**: `POST`
  - **Action**: Authenticate with the SuperAdmin credentials. 
  - *Result*: Saves the `access_token` into Postman variables.

### 2. Create Company
- **Request**: `02. Platform & Tenants / Companies (Company) / POST Create Company`
  - **Method**: `POST`
  - **Payload**:
    ```json
    {
      "name": "Pench Foods Pvt Ltd",
      "code": "PENCH"
    }
    ```
  - *Result*: Copy the returned `id` and save it to the `company_id` variable.

### 3. Create City-Tenant
- **Request**: `02. Platform & Tenants / Cities (City) / POST Create City`
  - **Method**: `POST`
  - **Payload**:
    ```json
    {
      "company": "{{company_id}}",
      "name": "Nagpur",
      "state": "Maharashtra",
      "code": "NGP",
      "timezone": "Asia/Kolkata",
      "require_pod": true
    }
    ```
  - *Result*: Copy the returned `id` and save it to `city_id`. A database schema named `nagpur` is automatically created and migrated, and the domain mapping (e.g. `nagpur.localhost`) is automatically created by the server.

---

## 🗺️ Phase 3: Regional Infrastructure (Tenant Schema)
> [!IMPORTANT]
> **Switch your Postman Environment `base_url` to `http://nagpur.localhost:8000`** (or `http://nagpur.localhost:8083`).
> All following requests route to the `nagpur` tenant database schema.

### 5. Create Zone
- **Request**: `02. Platform & Tenants / Zones (Zone) / POST Create Zone`
  - **Method**: `POST`
  - **Payload**:
    ```json
    {
      "name": "Dharampeth Zone",
      "description": "Dharampeth and Ram Nagar areas"
    }
    ```
  - *Result*: Copy the returned `id` and save it to `zone_id`.

### 6. Create Product
- **Request**: `04. Inventory & Warehousing / Products (Product) / POST Create Product`
  - **Method**: `POST`
  - **Payload**:
    ```json
    {
      "name": "A2 Gir Cow Milk (1 Litre)",
      "sku": "MILK-A2-1L",
      "unit_price": 108.00,
      "unit": "litre",
      "description": "Pure Gir Cow A2 Milk in Glass Bottle"
    }
    ```
  - *Result*: Copy the returned `id` and save it to `product_id`.

### 7. Initialize Warehouse and Stock
- **Request**: `04. Inventory & Warehousing / Warehouses (Warehouse) / POST Create Warehouse`
  - **Method**: `POST`
  - **Payload**: `{"name": "Dharampeth Depot", "address": "Dharampeth, Nagpur"}`
  - *Result*: Save the `id` to `warehouse_id`.
- **Request**: `04. Inventory & Warehousing / Stock Levels (Stock) / POST Create Stock`
  - **Method**: `POST`
  - **Payload**:
    ```json
    {
      "warehouse": "{{warehouse_id}}",
      "product": "{{product_id}}",
      "quantity": 500
    }
    ```

---

## 👥 Phase 4: Driver & Customer Registration (Tenant Schema)

### 8. Register and Set Up Driver
- **Request**: `01. Auth & Registration / User Registration (Templates) / Register: Driver`
  - **Method**: `POST`
  - **Action**: Register the driver credentials account.
  - *Result*: Copy the returned `id` to `driver_user_id`.
- **Request**: `06. Fleet & Driver Management / City Drivers (Driver) / POST Create Driver`
  - **Method**: `POST`
  - **Payload**:
    ```json
    {
      "user": "{{driver_user_id}}",
      "zone": "{{zone_id}}",
      "vehicle_number": "MH-49-AB-1234",
      "vehicle_type": "Mini Truck",
      "capacity_litres": 300
    }
    ```
  - *Result*: Copy the profile `id` to `driver_profile_id`.

### 9. Register and Set Up Customer
- **Request**: `01. Auth & Registration / User Registration (Templates) / Register: Customer (Mandatory Fields)`
  - **Method**: `POST`
  - **Action**: Register the customer login credentials.
  - *Result*: Copy the returned `id` to `customer_user_id`.
- **Request**: `03. CRM & Customers / Customers (Customer) / POST Create Customer`
  - **Method**: `POST`
  - **Payload**:
    ```json
    {
      "user": "{{customer_user_id}}",
      "zone": "{{zone_id}}",
      "first_name": "Aniket",
      "last_name": "Sharma",
      "address_line1": "12, Gokul Path, Dharampeth",
      "city_name": "Nagpur",
      "latitude": 21.1458,
      "longitude": 79.0882,
      "phone_number": "9876543210"
    }
    ```
  - *Result*: Copy the customer profile `id` to `customer_profile_id`.

---

## 📅 Phase 5: Subscriptions & Order Dispatch Prep

### 10. Create Customer Subscription
- **Request**: `09. Subscriptions / Subscriptions (Subscription) / POST Create Subscription`
  - **Method**: `POST`
  - **Payload**:
    ```json
    {
      "customer": "{{customer_profile_id}}",
      "frequency": "daily",
      "start_date": "2026-05-20",
      "items": [
        {
          "product": "{{product_id}}",
          "quantity": 2
        }
      ]
    }
    ```
  - *Result*: Copy the subscription `id` to `subscription_id`.

### 11. Trigger Order Generation (Cron Simulator)
- **Request**: `09. Subscriptions / POST Trigger Order Generation (Test)`
  - **Method**: `POST`
  - **Payload**:
    ```json
    {
      "target_date": "2026-05-20"
    }
    ```
  - *Result*: The system scans active subscriptions and generates `PENDING` orders for `2026-05-20`. 
- **Request**: `05. Logistics & Route Optimization / Orders (Order) / GET List Orders`
  - **Method**: `GET`
  - *Result*: Locate the generated order for the customer and copy the order `id` to `order_id`.

### 12. Create Optimized Delivery Route
- **Request**: `05. Logistics & Route Optimization / Routes (Route) / POST Create Optimized Route`
  - **Method**: `POST`
  - **Payload**:
    ```json
    {
      "date": "2026-05-20",
      "zone": "{{zone_id}}"
    }
    ```
  - *Result*: Uses OR-Tools to solve the TSP routing problem for all pending orders in Dharampeth Zone on this date. Saves the created route `id` to `route_id`.

---

## 🚚 Phase 6: Last-Mile Delivery Execution (Driver Flow)
> [!NOTE]
> **Authenticate as the Driver**: Run `01. Auth & Registration / POST Standard Login` using Driver credentials. The `access_token` now has Driver permissions.

### 13. Driver Check-In & Get Route
- **Request**: `00. SPECIAL: Driver Mobile App / POST Driver Check-in`
  - **Method**: `POST`
  - **Action**: Marks the driver as active for the day.
- **Request**: `00. SPECIAL: Driver Mobile App / GET My Active Route`
  - **Method**: `GET`
  - *Result*: Returns the list of sorted delivery drops and paths.

### 14. Start Delivery Trip
- **Request**: `00. SPECIAL: Driver Mobile App / POST Start Trip`
  - **Method**: `POST`
  - **Payload**: `{"route_id": "{{route_id}}"}`
  - *Result*: Orders change from `PENDING` to `IN_TRANSIT`.

### 15. Submit Proof of Delivery (POD)
- **Request**: `00. SPECIAL: Driver Mobile App / POST Submit Delivery`
  - **Method**: `POST`
  - **Body**: `form-data`
    - `order_id`: `{{order_id}}`
    - `status`: `delivered`
    - `pod_image`: *(Upload a sample image file)*
    - `pod_latitude`: `21.1458`
    - `pod_longitude`: `79.0882`
  - *Result*: Order is updated to `DELIVERED`.

### 16. Complete Trip
- **Request**: `00. SPECIAL: Driver Mobile App / POST Complete Trip`
  - **Method**: `POST`
  - **Payload**: `{"route_id": "{{route_id}}"}`

---

## 📊 Phase 7: Reconciliation & Billing (Admin Flow)
> [!NOTE]
> **Authenticate as Admin**: Log back in using SuperAdmin/Staff credentials.

### 17. Daily Route Reconciliation
- **Request**: `05. Logistics & Route Optimization / Routes (Route) / POST Generate Reconciliation`
  - **Method**: `POST`
  - **Payload**: `{"route_id": "{{route_id}}"}`
- **Request**: `05. Logistics & Route Optimization / Reconciliations / POST Reconcile`
  - **Method**: `POST`
  - **Payload**:
    ```json
    {
      "route": "{{route_id}}",
      "cash_collected": 216.00,
      "discrepancy_reason": ""
    }
    ```

### 18. Generate Monthly Bills
- **Request**: `08. Finance & Billing / Monthly Bills (MonthlyBill) / POST Trigger Billing Generation`
  - **Method**: `POST`
  - **URL**: `{{city_url}}/api/erp/finance/bills/trigger-generation/`
  - **Payload**:
    ```json
    {
      "year": 2026,
      "month": 5
    }
    ```
- **Request**: `08. Finance & Billing / Monthly Bills (MonthlyBill) / GET List Bills`
  - **Method**: `GET`
  - **URL**: `{{city_url}}/api/erp/finance/bills/` (You can also filter by customer: `?customer={{customer_id}}` or status: `?status=unpaid`)
