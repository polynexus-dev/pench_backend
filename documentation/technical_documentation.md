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
- **Permission Classes**: `HasGroupPermission` ensures API security based on group membership and user flags.

### Authentication & Security
- **JWT**: `rest_framework_simplejwt` for API authentication.
- **Token Lifetime**: Access tokens are strictly valid for **1 day (24 hours)**.
- **Lifecycle Tracking**: Every API response includes `expires_in_seconds`, allowing frontends to manage session expiration gracefully.
- **OTP**: Custom OTP model for secure phone-based logins for drivers and customers.

### Database
- **Engine**: PostgreSQL with PostGIS extension.
- **Spatial Data**: Uses `GeoDjango` and `PolygonField` for geographic zone management.

### Logistics Engine
- **Optimization**: Google OR-Tools for solving the Traveling Salesman Problem (TSP) and Vehicle Routing Problem (VRP).
- **Logic**: Routes are generated based on customer coordinates and optimized for distance.

### Real-time Features
- **Channels**: Django Channels with Redis back-end for real-time tracking updates (WebSocket).
- **Celery**: Background tasks for route generation and automated reports.

## App Descriptions

### `accounts`
Handles user registration, authentication, and global RBAC permissions.

### `tenants`
Defines cities (tenants) and domains. Also manages geographic zones within each city.

### `orders`
The core of the system. Manages orders, delivery schedules, and optimized routes.

### `inventory`
Tracks products, categories, and returnable assets (bottles).

### `routing`
Handles specific logistics logic and distance calculations.

### `administration`
Tenant-specific feature toggles and configuration (Theme colors, support contacts).

## Deployment
- **Containerization**: Docker and Docker Compose (see `Dockerfile` and `docker-compose.yml`).
- **Web Server**: Daphne (for ASGI/Channels) and WSGI for standard requests.
