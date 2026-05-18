# 🥛 Pench Logistics ERP: Object Dependencies & Data Flow Guide

This document defines the step-by-step model creation sequence, database constraints, and operational dependencies of the **Pench Logistics ERP** system. 

It is designed to give developers, administrators, and integrations teams a clear understanding of what data must exist before performing specific business actions.

---

## 🏗️ 1. Complete Operational Dependency Diagram

The diagram below shows the high-level progression of data creation. Each block *must* be fully set up before moving to the next.

```mermaid
graph TD
    %% Base Schema Configuration
    subgraph Phase 1: Global Infrastructure (Public Schema)
        A[City / Tenant Schema] --> B[Domain / Subdomain mapping]
        B --> C[SuperAdmin / Global User]
    end

    %% Tenant Schema Configuration
    subgraph Phase 2: Regional Setup (Tenant Schema)
        C --> D[Zone Definition]
        D --> E[Products & Inventory]
        D --> F[Departments & HR Employees]
    end

    %% Accounts & Profiles Setup
    subgraph Phase 3: Core Profiles & Operations
        F --> G[Driver Profile]
        D --> G
        D --> H[Customer Profile]
        H --> I[Active Subscription]
        E --> I
    end

    %% Workflow Progression
    subgraph Phase 4: Delivery Workflow
        I --> J[Order Generation - 4 AM]
        J --> K[Optimized Route - 6 AM]
        G --> K
        K --> L[Live WebSocket Tracking]
        K --> M[Proof of Delivery / POD]
        M --> N[Daily Reconciliation]
    end

    style A fill:#e1f5fe,stroke:#03a9f4,stroke-width:2px;
    style G fill:#fff8e1,stroke:#ffb300,stroke-width:2px;
    style H fill:#fff8e1,stroke:#ffb300,stroke-width:2px;
    style K fill:#e8f5e9,stroke:#4caf50,stroke-width:2px;
    style N fill:#ffebee,stroke:#f44336,stroke-width:2px;
```

---

## 🔄 2. Step-by-Step Object Creation Sequence

For the ERP system to function cleanly without raising database validation errors (such as `IntegrityError` or `ValidationError`), you **must** create records in this exact sequence:

### Step 1: Base Tenant Infrastructure (Public Schema)
1. **City (`tenants.City`)**: 
   * *Dependencies*: None.
   * *Explanation*: The city represents the tenant schema in the database.
2. **Domain (`tenants.Domain`)**:
   * *Dependencies*: Requires a **City**.
   * *Explanation*: Maps a specific subdomain (e.g., `nagpur.pench.in` or `localhost`) to the City schema for routing.

### Step 2: Geographic & Inventory Foundations (Tenant Schema)
3. **Zone (`routing.Zone`)**:
   * *Dependencies*: Requires a **City**.
   * *Explanation*: Defines geographic operational sectors inside a city (used for geofencing and assigning permanent drivers).
4. **Product (`inventory.Product`)**:
   * *Dependencies*: None (can optionally link to returnable `BottleType`).
   * *Explanation*: The physical product catalogue (e.g. Milk bottle, Paneer).

### Step 3: User Accounts & Profiles (Public/Tenant Linkage)
5. **Driver User Account (`accounts.User`)**:
   * *Dependencies*: None.
   * *Explanation*: An auth account with the `is_driver` flag set to `True`.
6. **Driver Profile (`routing.Driver`)**:
   * *Dependencies*: Requires a **Driver User Account** AND a **Zone**.
   * *Explanation*: Links the user login account to vehicle details (plate, capacity) and binds them permanently to an operational zone.
7. **Customer User Account (`accounts.User`)**:
   * *Dependencies*: None (automatically created during app onboarding).
   * *Explanation*: An auth account with the `is_customer` flag set to `True`.
8. **Customer Profile (`crm.Customer`)**:
   * *Dependencies*: Requires a **Customer User Account** AND a **Zone**.
   * *Explanation*: Houses delivery coordinates, addresses, QR codes, and geolocates the customer within a delivery zone.

### Step 4: Recurring Subscriptions & Automatic Orders
9. **Subscription (`subscriptions.Subscription`)**:
   * *Dependencies*: Requires a **Customer Profile** AND one or more **Products**.
   * *Explanation*: Schedules recurring delivery frequencies (Daily, Alternate, Custom days).
10. **Order (`orders.Order`)**:
    * *Dependencies*: Requires a **Customer Profile** AND **Products** (optionally spawned from a **Subscription**).
    * *Explanation*: A scheduled delivery record for a specific date containing order line items.

### Step 5: Logistics Dispatch & Execution
11. **Route (`routing.Route`)**:
    * *Dependencies*: Requires a **Driver Profile** AND one or more active **Orders**.
    * *Explanation*: **Crucial Rule:** *Without an assigned driver and at least one pending order in the zone, a Route cannot be generated.*
12. **Tracking Event & Trail (`routing.TrackingEvent` / `tracking.DriverTrail`)**:
    * *Dependencies*: Requires an active **Route** and **Driver Profile**.
    * *Explanation*: Stores snap-to-road trails and WebSocket positions only while a trip is active.
13. **Daily Reconciliation (`routing.DailyReconciliation`)**:
    * *Dependencies*: Requires a completed **Route** and **Driver Profile**.
    * *Explanation*: Created at the end of the shift to verify cash and digital transactions collected during the trip.

---

## 📊 3. Detailed Model Dependency Reference

Below is a detailed cross-reference of the main ERP models, listing exactly what they are dependent on, and the technical consequence if those dependencies are missing.

| Model Name | App | Primary Foreign Key Dependencies | Dependency Type | Consequence If Missing |
| :--- | :--- | :--- | :--- | :--- |
| **City** | `tenants` | None | Base | Cannot route requests; no tenant database schemas will exist. |
| **Domain** | `tenants` | `City` | **Strict** | Django-Tenants cannot resolve subdomains; requests default to a 404. |
| **HolidayCalendar** | `tenants` | `City` | Optional | Admin cannot set city-specific skipped delivery dates. |
| **User** | `accounts` | None | Base | No users can register, login, or obtain authentication tokens. |
| **Employee** | `hr` | `User`, `Department` | **Strict** | Cannot manage staff profiles, salaries, attendance, or payrolls. |
| **Zone** | `routing` | `City` (via schema), `User` (primary driver) | Optional | Cannot isolate deliveries geofencing boundaries or auto-dispatch drivers. |
| **Driver** | `routing` | `User` (Driver profile), `Zone` | **Strict** | Cannot register vehicles, allocate logistics capacity, or optimize routes. |
| **Customer** | `crm` | `User` (Customer login), `Zone` | **Strict** | Geolocation fails, driver cannot locate address, and no subscriptions can be made. |
| **Subscription** | `subscriptions` | `Customer`, `Product` | **Strict** | No orders can be auto-generated at 4 AM; delivery schedules fail. |
| **Order** | `orders` | `Customer`, `Subscription` (optional) | **Strict** | Cannot load delivery schedules, record POD proof, or track route items. |
| **Route** | `routing` | `Driver`, `Order` (ManyToMany) | **Strict** | OR-Tools routing engine fails; driver has no dashboard trip to start. |
| **TrackingEvent** | `routing` | `Route`, `Order` | **Strict** | Proof of Delivery (POD) photo, signature, and coordinates cannot be saved. |
| **DailyReconciliation**| `routing` | `Driver`, `Route` | **Strict** | Cannot balance cash collected against digital payments to complete shifts. |
| **DriverLocation** | `tracking` | `Driver` | **Strict** | WebSocket live location dashboard shows driver offline or loses maps coordinates. |

---

## 🚫 4. Strict System Constraints & Rules

1. **The Route Optimization Barrier**:
   * *Rule*: You cannot call the `api/ems/routes/create-optimized/` endpoint unless:
     * There is at least one active `Driver` available in the city.
     * There are active `Order` records marked as `pending` for the target delivery date.
     * The driver and orders exist inside the same geographic **Zone** boundaries.

2. **The Smart Onboarding Redirect Rule**:
   * *Rule*: When a Customer or Driver registers, they register globally on the public schema. However, **unless they are linked to a specific city-tenant schema via their Tenant Domain, they cannot access operational data** like products, active routes, or billing ledger histories.

3. **Geofenced Safe Boundary Constraint**:
   * *Rule*: You cannot create a `Zone` with coordinates outside of the Assigned `City` boundary polygon. The backend automatically calculates spatial intersection to prevent drivers from being misrouted outside of district limits.

4. **The "Hard-Pause" Delivery Freeze**:
   * *Rule*: At 4 AM, the automated generation task skips order creation for any customer whose subscription is marked `is_paused = True` or whose schedule falls within a registered `pause_start` and `pause_end` vacation period.

---
*Created for Pench Logistics ERP — Reference for Data Quality Management*
