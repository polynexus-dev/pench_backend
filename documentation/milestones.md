# Project Milestones

This document tracks the major milestones completed in the Pench Backend project.

## Completed Milestones

### 1. Core Architecture & Multi-Tenancy
- [x] Initialized Django project with `django-tenants`.
- [x] Configured shared vs. tenant app separation.
- [x] Implemented City/Domain routing for dynamic schema switching.
- [x] Setup PostgreSQL with PostGIS for spatial data support.

### 2. Authentication & Identity Management
- [x] **[ENHANCED]** Global Identity Model: All users (Admins, Drivers, Customers) managed centrally in the Public schema.
- [x] Phone-based OTP authentication system.
- [x] JWT integration with 1-day token validity.
- [x] **[NEW]** Token Lifecycle Tracking: API-level `expires_in_seconds` injection in all responses.
- [x] **[NEW]** Granular RBAC: Automated group synchronization (SuperAdmin, Managers, Drivers, Customers).

### 3. CRM & Customer Management
- [x] Lead management system.
- [x] Customer profiling with geographic location (GIS).
- [x] Subscription plans and customer assignment.
- [x] Automated role linking: CRM customers automatically assigned the `Customers` role globally.

### 4. Logistics & Order Management
- [x] Order lifecycle (Pending -> Confirmed -> In Transit -> Delivered).
- [x] Delivery scheduling and frequency management.
- [x] Proof of Delivery (POD) photo upload requirement.
- [x] Route optimization using Google OR-Tools.
- [x] Real-time tracking events for orders.

### 5. Inventory & Assets
- [x] Product and Category management.
- [x] Reusable bottle tracking (Issued vs. Returned).
- [x] Stock adjustment and transaction logs.

### 6. Administration & Security
- [x] Centralized Admin Configuration module.
- [x] Singleton settings for feature toggles (POD, Auto-assignment, etc.).
- [x] **[NEW]** SuperAdmin Privilege: Unrestricted access across all city tenants and services.
- [x] **[NEW]** Automated Role Setup: Server-startup group initialization for zero-config deployments.

## Current Focus
- [ ] Mobile App integration for Drivers and Customers.
- [ ] Advanced Finance & Billing reconciliation.
