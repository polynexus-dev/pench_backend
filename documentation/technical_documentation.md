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

### Database
- **Engine**: PostgreSQL with PostGIS extension.
- **Spatial Data**: Uses `GeoDjango` and `PolygonField` for geographic zone management.

### Authentication
- **System**: Custom User model extending `AbstractUser`.
- **JWT**: `rest_framework_simplejwt` for API authentication.
- **OTP**: Custom OTP model for phone-based logins.

### Logistics Engine
- **Optimization**: Google OR-Tools for solving the Traveling Salesman Problem (TSP) and Vehicle Routing Problem (VRP).
- **Logic**: Routes are generated based on customer coordinates and optimized for distance.

### Real-time Features
- **Channels**: Django Channels with Redis back-end for real-time tracking updates (WebSocket).
- **Celery**: Background tasks for route generation and automated reports.

## App Descriptions

### `accounts`
Handles user registration, authentication, and portal-specific permissions.

### `tenants`
Defines cities (tenants) and domains. Also manages geographic zones within each city.

### `orders`
The core of the system. Manages orders, delivery schedules, and optimized routes.

### `inventory`
Tracks products, categories, and returnable assets (bottles).

### `routing`
Handles specific logistics logic and distance calculations.

### `administration`
New module for tenant-specific feature toggles and configuration.

## Deployment
- **Containerization**: Docker and Docker Compose (see `Dockerfile` and `docker-compose.yml`).
- **Web Server**: Daphne (for ASGI/Channels) and WSGI for standard requests.
