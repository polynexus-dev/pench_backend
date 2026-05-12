# Technical Documentation

## Overview
Pench Backend is a multi-tenant ERP and Logistics platform built using Django. It supports multiple city-based schemas within a single database instance, providing isolation for city-level data while sharing core infrastructure.

## Architecture

### Multi-Tenancy
- **Framework**: `django-tenants`
- **Isolation Strategy**: Schema-based isolation.
- **Tenant Model**: `tenants.City`
- **Domain Model**: `tenants.Domain`
- **Shared Apps**: `accounts`, `tenants`, `core` (Public Schema).
- **Tenant Apps**: `crm`, `orders`, `inventory`, `finance`, `hr`, `routing`, `tracking`, `administration` (Tenant Schema).

### Identity & Access Control (RBAC)
- **Centralized Identity**: All users are stored in the `public` schema (`accounts.User`).
- **Roles**: 
    - **SuperAdmin**: Unrestricted global access (Public & Tenants).
    - **Managers**: Granular access to specific modules (Inventory, Logistics, HR, etc.) via Django Groups.
    - **Drivers**: Mobile-app access for trip management and tracking.
    - **Customers**: Limited access to their own orders and subscription portal.
- **Permission Classes**: `HasGroupPermission` ensures API security based on group membership.

### Authentication & Security
- **JWT**: `rest_framework_simplejwt` for API authentication.
- **Token Lifetime**: Access tokens are strictly valid for **1 day (24 hours)**.
- **OTP**: Custom OTP model for secure phone-based logins (Drivers/Customers).
- **API Metadata**: Every response includes `expires_in_seconds` for session management.

## Complete Operational Flow

The following describes the end-to-end lifecycle of the Pench delivery ecosystem:

### 1. Tenant & System Initialization
- **City Setup**: SuperAdmin creates a new `City` (Tenant) and links a `Domain`.
- **Role Sync**: The system automatically initializes standard Groups (SuperAdmin, Staff, Manager, Driver, Customer) on first run.
- **Zone Definition**: Managers define geographic zones (`PolygonField`) for delivery coverage.

### 2. User Onboarding & CRM
- **Lead Generation**: Potential customers are added as Leads in the `crm` module.
- **Conversion**: Leads are converted to `Customers` with precise GIS location pinning.
- **Identity Link**: Each customer is linked to a global `User` account for portal access.

### 3. Subscription & Order Generation
- **Plan Assignment**: Customers subscribe to specific product plans (e.g., Daily Milk).
- **Auto-Generation**: Orders are automatically generated based on the subscription frequency or manually created by Managers.
- **Inventory Check**: System verifies product availability across warehouses.

### 4. Logistics & Route Optimization
- **Trip Creation**: Orders are grouped into Trips for a specific delivery date.
- **Optimization**: The `routing` engine uses Google OR-Tools and OSRM to generate the most efficient delivery sequence (TSP).
- **Driver Assignment**: Trips are assigned to specific `Drivers` based on availability.

### 5. Driver Execution (Mobile App)
- **Login**: Drivers authenticate via OTP.
- **Route Tracking**: The app uses a WebView-based Leaflet integration to display the optimized route and live location.
- **Live Streaming**: Real-time GPS coordinates are streamed to the backend for monitoring.

### 6. Delivery Fulfillment
- **QR Verification**: Upon arrival, the driver must scan a QR code at the delivery point to verify location.
- **POD Upload**: Proof of Delivery (POD) photos are uploaded as evidence.
- **Atomic Transaction**: Once "Delivered" is triggered:
    1. Order status updates to `delivered`.
    2. Inventory is deducted (including bottle returns).
    3. Invoice is automatically generated in the `finance` module.

---

## App Descriptions

### `accounts`
Handles user registration, authentication, and global RBAC permissions.

### `tenants`
Defines cities (tenants) and domains. Also manages geographic zones.

### `orders`
Manages order lifecycle, delivery schedules, and trip groupings.

### `inventory`
Tracks products, categories, and returnable assets (bottles).

### `routing` & `tracking`
Handles logistics optimization, GPS events, and live tracking visualization.

### `administration`
Tenant-specific configurations (Theme, POD requirements, support).

## Deployment
- **Containerization**: Docker / Docker Compose.
- **Web Server**: Daphne (ASGI) for WebSockets and WSGI for REST.
