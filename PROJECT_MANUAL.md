# 🥛 Pench Logistics ERP: Zero to Hero Manual

Welcome to the **Pench Logistics ERP** documentation. This system is a high-performance, multi-tenant backend designed for dairy and recurring delivery businesses.

---

## 🏗️ 1. Architecture: The Foundation
The system uses a **Multi-Tenant (Shared Database, Separate Schemas)** architecture.

*   **Public Schema**: Stores global users (SuperAdmins), cities, and domains.
*   **Tenant Schemas (City-specific)**: Each city (Nagpur, Pune, etc.) has its own private set of tables (Customers, Orders, Inventory).
*   **Security**: Data is physically isolated. A manager in Nagpur can never see data from Pune.

---

## 📦 2. Key Modules
### 👥 CRM & Accounts
*   **Smart Login**: Drivers and Customers log in via the public domain; the system automatically detects their city and redirects them to the correct dashboard.
*   **OTP Authentication**: Secure login via mobile number.

### 📅 Subscription Management
*   **Flexible Frequencies**: Daily, Alternate Days, Weekdays, and Custom (e.g., Mon/Wed/Fri).
*   **Vacation Mode**: Customers can schedule pauses. The system automatically resumes deliveries once the vacation ends.
*   **Automatic Generation**: Every night at 4 AM, the system creates the next day's orders based on active subscriptions.

### 🚚 Logistics & Routing
*   **Zones & Driver Persistence**: Cities are divided into geographic Zones. Each Driver is permanently assigned to a Zone, ensuring they know their regular customers and routes perfectly.
*   **OR-Tools Optimization**: Automatically calculates the most fuel-efficient route within each Zone.
*   **Live Tracking**: Drivers' GPS locations are streamed via WebSockets to the Admin dashboard.
*   **Geotagged POD**: Proof of Delivery includes a photo and the exact GPS coordinates where the photo was taken.

---

## 🔄 3. The Daily Workflow (Zero to Hero)

### Step 1: Order Generation (4 AM)
The system runs a background task that scans all city subscriptions. It creates `PENDING` orders for all active customers.

### Step 2: Route Dispatch (6 AM)
The Admin reviews the `PENDING` orders. Because each customer is linked to a **Zone**, the system automatically suggests the **Assigned Driver** for that zone. The Admin clicks "Optimize Route" to give the driver the best path.

### Step 3: Driver Check-in
The driver logs into the **Mobile App**. They see their "Active Route". They click **"Start Trip"**, which moves all orders from `PENDING` to `IN_TRANSIT`.

### Step 4: Last-Mile Delivery
The driver follows the map. At each house:
1.  They deliver the product.
2.  (Optional) They take a **Proof of Delivery** photo.
3.  They click **"Submit Delivery"**. The order status changes to `DELIVERED`.

### Step 5: Trip Completion
Once the last delivery is made, the driver clicks **"Complete Trip"**. The Admin can now see the final summary and the "Trail" of the driver's actual road path.

---

## 🛠️ 4. Administration & Configuration
Admins have "Solo" control over their city:
*   **Mandatory POD**: Can be turned on/off.
*   **Holidays**: Admins can set city-specific holidays to skip all deliveries.
*   **Domain Management**: Admins can map custom subdomains (e.g., `nagpur.pench.in`) to their tenant.

---

## 🚀 5. The Future Roadmap (Phase 2)
To take this from a logistics tool to a massive platform, we recommend:

1.  **💰 Wallet & Ledger**:
    *   Prepaid balance for customers.
    *   Automatic "No Balance, No Milk" pausing logic.
2.  **🔔 Push Notifications**:
    *   FCM/Firebase integration for real-time delivery alerts.
3.  **📦 Inventory Check-In**:
    *   A "Stock Load" feature where drivers must confirm the quantity of milk loaded into the van before starting.
4.  **📊 Advanced Analytics**:
    *   Heatmaps of delivery density.
    *   Wastage tracking (Returned vs Delivered).
5.  **💬 WhatsApp Business API**:
    *   Sending daily summaries and bill alerts directly to WhatsApp.

---

## 👨‍💻 Technical Notes for Developers
*   **Framework**: Django + Django-Tenants.
*   **Database**: PostgreSQL + PostGIS (for mapping).
*   **Routing Engine**: OSRM (Open Source Routing Machine).
*   **Real-time**: Django Channels (WebSockets).

---

## 📊 6. Schema Visualization
To understand the graphical dependencies of this project, you can generate a database diagram:

1.  **Install Graphviz**: Download from graphviz.org.
2.  **Generate Diagram**:
    ```bash
    python manage.py graph_models -a -o project_schema.png
    ```
    *This creates a PNG file showing all models and their Foreign Key relationships.*

## 🛡️ 7. Geo-Fencing & City Boundaries
The system prevents admins from creating delivery zones outside of their assigned city district.

1.  **Set City Boundary**: Use the `api/erp/tenants/cities/` endpoint to set a Polygon boundary for the city.
2.  **Zone Validation**: All zones created via `api/ems/zones/` are automatically validated against this boundary.
3.  **Importing GIS Files**: Use the `LayerMapping` tool or GeoJSON exports to populate these boundaries from Shapefiles/KML.

## 🚀 8. VM Deployment & Migrations
When deploying to a VM or a new environment, follow this exact sequence:

1.  **Pull latest code**: Ensure all migration files (in `tenants/migrations`, `routing/migrations`, etc.) are present.
2.  **Migrate Public Data**:
    ```bash
    python manage.py migrate_schemas --shared
    ```
3.  **Migrate Tenant Data**:
    ```bash
    python manage.py migrate_schemas --tenant
    ```

---
*Manual Version 1.3 — Finalized with Deployment Guide*
