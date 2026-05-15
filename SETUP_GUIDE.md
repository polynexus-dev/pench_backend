# 🗺️ Pench ERP: New City Setup Guide

This guide outlines the **exact order** of operations required to set up a new city from zero to full delivery operations.

---

## Phase 1: Global Setup (Public Schema)
*Required to create the "Container" for the city.*

1.  **Admin Login**: Login as SuperAdmin on the public portal.
2.  **Create City (Tenant)**:
    *   Endpoint: `/api/erp/tenants/cities/`
    *   This creates the Database Schema and runs migrations automatically.
3.  **Create Domain**:
    *   Endpoint: `/api/erp/tenants/domains/`
    *   Link the domain (e.g., `pune.pench.in`) to the City you just created.

---

## Phase 2: City Infrastructure (Tenant Schema)
*Required to define the area and the goods.*

4.  **Create Zones**:
    *   Endpoint: `/api/ems/zones/`
    *   Define areas like "West Pune", "East Pune". You need these before you can assign customers.
5.  **Create Products**:
    *   Endpoint: `/api/erp/inventory/products/`
    *   Add your catalog (Milk, Ghee, etc.). Prices are city-specific, allowing you to have different rates for Nagpur vs Pune.

---

## Phase 3: Team & Customers (Tenant Schema)
*Required to build the delivery network.*

6.  **Create Driver User**:
    *   Endpoint: `/api/accounts/register/` (Set `role="Drivers"`)
    *   **New**: You can now pass `"zone": "uuid"` in this payload to automatically assign the driver to their area.
7.  **Create Customer Profile**:
    *   Endpoint: `/api/accounts/register/` (Set `role="Customers"`)
    *   **Assign Zone**: In the CRM profile, link the customer to their specific Zone. This is what automates the driver's route later.

---

## Phase 4: Active Operations
*The daily recurring cycle.*

9.  **Create Subscription**:
    *   Endpoint: `/api/erp/subscriptions/`
    *   Link the Customer, Products, and Frequency (Daily, Alternate, etc.).
10. **Order Generation**:
    *   The system will automatically generate orders at 4 AM.
    *   (Manual trigger for testing): Use the `/trigger-generation/` endpoint.
11. **Route Optimization**:
    *   Endpoint: `/api/erp/orders/routes/optimize/`
    *   The system will group orders by **Zone** and assign them to the **Zone's Driver**.

---

## 💡 Dependency Summary:
*   **City** → must exist before → **Zone**
*   **Zone** → must exist before → **Customer Assignment**
*   **Product** → must exist before → **Subscription**
*   **Driver** → must exist before → **Zone Assignment**
*   **Zone & Customer** → must exist before → **Automated Route Optimization**

---
*Follow this flow to ensure no data integrity errors during setup.*
