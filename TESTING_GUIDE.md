# 🧪 Pench ERP: End-to-End Testing Guide

This guide provides the sequence, endpoints, and sample payloads required to verify every feature in the system. Use this to verify your setup or as a base for automated tests.

---

## 🔐 1. Authentication (Public Domain)
*Verify identity management.*

### A. Request OTP
*   **URL**: `POST /api/accounts/request-otp/`
*   **Payload**: `{"phone": "9876543210"}`
*   **Result**: 200 OK.

### B. Login with OTP
*   **URL**: `POST /api/accounts/login-otp/`
*   **Payload**: `{"phone": "9876543210", "code": "123456"}`
*   **Result**: Returns `access` token, `sid` (schema), and `domain_name`.

---

## 🏙️ 2. Multi-Tenant Setup (Public Domain)
*Requires SuperAdmin token.*

### A. Create City
*   **URL**: `POST /api/erp/tenants/cities/`
*   **Payload**: `{"name": "Nagpur", "schema_name": "nagpur"}`

### B. Create Domain
*   **URL**: `POST /api/erp/tenants/domains/`
*   **Payload**: `{"domain": "nagpur.192.168.1.199.nip.io", "tenant": "nagpur_uuid"}`

---

## 🗺️ 3. City Infrastructure (City Domain)
*Requires City Admin token.*

### A. Create Zone
*   **URL**: `POST /api/ems/zones/`
*   **Payload**: `{"name": "North Zone", "description": "Dharampeth Area"}`

### B. Create Product
*   **URL**: `POST /api/erp/inventory/products/`
*   **Payload**: `{"name": "Cow Milk (1L)", "sku": "MILK-1L", "unit_price": 60.00, "unit": "liter"}`

---

## 👥 4. Users & Drivers (City Domain)

### A. Register Driver
*   **URL**: `POST /api/accounts/register/`
*   **Payload**: `{"username": "driver1", "phone": "9000000001", "role": "Drivers", "tenant_schema": "nagpur"}`

### B. Assign Driver to Zone
*   **URL**: `PATCH /api/ems/zones/{zone_id}/`
*   **Payload**: `{"assigned_driver": "user_uuid"}`

### C. Register Customer
*   **URL**: `POST /api/accounts/register/`
*   **Payload**: `{"username": "cust1", "phone": "9000000002", "role": "Customers", "tenant_schema": "nagpur"}`

### D. Map Customer to Zone
*   **URL**: `PATCH /api/erp/customers/{cust_id}/`
*   **Payload**: `{"zone": "zone_uuid"}`

---

## 📅 5. Subscriptions (City Domain)

### A. Create Subscription
*   **URL**: `POST /api/erp/subscriptions/`
*   **Payload**: 
    ```json
    {
      "customer": "cust_uuid",
      "frequency": "daily",
      "start_date": "2026-05-15",
      "items": [{"product": "product_uuid", "quantity": 1}]
    }
    ```

### B. Add Vacation
*   **URL**: `POST /api/erp/subscriptions/{sub_id}/vacation/`
*   **Payload**: `{"pause_start": "2026-05-20", "pause_end": "2026-05-25"}`

---

## 🚚 6. Delivery Workflow (City Domain)

### A. Trigger Order Generation (Admin)
*   **URL**: `POST /api/erp/subscriptions/trigger-generation/`
*   **Payload**: `{"target_date": "2026-05-16"}`

### B. Optimize Route (Admin)
*   **URL**: `POST /api/ems/routes/optimize_all/` (or individual route optimize)
*   **Result**: Orders are assigned sequence numbers.

### C. Start Trip (Driver)
*   **URL**: `POST /api/ems/routes/{route_id}/start_trip/`
*   **Result**: All orders move to `IN_TRANSIT`.

### D. Proof of Delivery (Driver)
*   **URL**: `POST /api/ems/drivers/{order_id}/submit-delivery/`
*   **Payload (FormData)**: 
    *   `pod_image`: [File]
    *   `pod_latitude`: 21.1458
    *   `pod_longitude`: 79.0882
*   **Result**: Status moves to `DELIVERED`.

---

## 📊 7. Monitoring & Tracking

### A. Live Tracking (Admin)
*   **WebSocket**: `ws://domain/ws/tracking/{route_id}/`
*   **Result**: Stream of lat/lon updates.

### B. Monthly Summary (Customer)
*   **URL**: `GET /api/erp/subscriptions/{sub_id}/monthly-summary/?month=5&year=2026`
*   **Result**: Color-coded calendar showing all delivery statuses.

---
*Testing this full flow ensures that your system is production-ready.*
