# Project Milestones

This document tracks the major milestones completed in the Pench Backend project.

## Completed Milestones

### 1. Core Architecture & Multi-Tenancy
- [x] Initialized Django project with `django-tenants`.
- [x] Configured shared vs. tenant app separation.
- [x] Implemented City/Domain routing for dynamic schema switching.
- [x] Setup PostgreSQL with PostGIS for spatial data support.

### 2. Authentication & Identity Management
- [x] Custom User model with portal-specific flags (`is_erp_user`, `is_driver`).
- [x] Phone-based OTP authentication system.
- [x] JWT integration for secure API access.
- [x] Role-Based Access Control (RBAC) via custom permissions.

### 3. CRM & Customer Management
- [x] Lead management system.
- [x] Customer profiling with geographic location (GIS).
- [x] Subscription plans and customer assignment.

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

### 6. Administration & Governance
- [x] **[LATEST]** Centralized Admin Configuration module.
- [x] Singleton settings for feature toggles (POD, Auto-assignment, etc.).
- [x] Simplified user permission management via administration proxy.

## Current Focus
- [ ] Completing technical documentation and user manuals.
- [ ] Enhancing Postman collection with detailed examples.
