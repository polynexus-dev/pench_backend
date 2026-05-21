# Pench Dairy Project: Comprehensive Codebase Audit

This document provides a thorough audit of the backend (`pench_backend`) and frontend (`Pench_Food_Frontend`) codebases. It details active features, highlights gaps where the frontend is using mock data or placebo (non-existent) endpoints, lists completely unmapped modules, and outlines a technical roadmap for future expansion.

---

## 1. Executive Summary & Core Gaps

The backend is built as a highly robust, multi-tenant Django application using `django-tenants` and a PostgreSQL database (supporting PostGIS for spatial operations). It has comprehensive support for HR, payroll, taxation/GST, finance, subscription rules, route optimization, and GPS trails.

The frontend is a beautifully designed React/Vite dashboard featuring highly polished UI components. However, there are significant architectural gaps where the frontend is completely decoupled from the backend databases, relying on **mock data or placebo (non-existent) endpoints**.

### Top 3 Critical Gaps:
1. **Placebo Custom Discounts:** The frontend attempts to patch `/api/erp/customers/{id}/` with a single custom percentage `discount_rate`. However, this field does not exist in the backend `Customer` model or serializer and is silently discarded. The backend actually has a rich `CustomerProductPrice` system for per-product custom rates, which is completely unexposed in the UI.
2. **Mocked Subscriptions:** The Subscriptions tab in the customer profile page renders pure mock data generated client-side from deterministic customer ID seeds. It has no connection to the backend `subscriptions` app database tables.
3. **Mocked Payment History:** The Payment History tab in the customer profile renders mock transactions client-side, completely ignoring the backend's real `finance` invoices and payment registers.

---

## 2. Gaps & Partially Implemented Features

Below is a detailed breakdown of components that exist in both codebases but are mismatched, mocked, or under-implemented.

### A. Customer Custom Discounts
*   **Frontend Implementation:** In `CustomerProfileTab.tsx` (lines 205–241, 794–938), the admin can input a custom discount percentage rate. On submit, it sends a PATCH to `/erp/customers/{id}/` with `{ discount_rate: numericValue }`.
*   **Backend Reality:** The `Customer` model in `crm/models.py` **does not have a `discount_rate` field**. It is not defined in `CustomerSerializer` and is ignored by Django.
*   **Backend Alternative (Unexposed):** The backend has a robust per-customer, per-product custom pricing table `CustomerProductPrice` in the `inventory` app (routed at `/api/inventory/customer-prices/`). This supports precise discount rates and absolute custom overrides for each item.
*   **Resolution Needed:** Refactor the frontend "Custom Discount" UI to list the product catalog and perform POST/PATCH/DELETE requests against the `/api/inventory/customer-prices/` endpoint.

### B. Customer Subscriptions
*   **Frontend Implementation:** In `CustomerProfileTab.tsx` (lines 64, 91–136), customer subscriptions are dynamically generated in memory from character codes of the customer's ID.
*   **Backend Reality:** The `subscriptions` app contains fully working database models (`Subscription`, `SubscriptionItem`, `SubscriptionSkipDate`) and endpoints (`/api/subscriptions/`). It handles:
    *   Daily, Alternate, Weekday, Weekend, and Custom weekday scheduling.
    *   Vacation / pause date ranges (`/api/subscriptions/{id}/pause/` and `/api/subscriptions/{id}/resume/`).
    *   Skipping specific dates (`SubscriptionSkipDate`).
    *   Updating quantity per item (`/api/subscriptions/{id}/update-quantity/`).
*   **Resolution Needed:** Replace the mock subscription generator in the customer profile with a real GET fetch to `/api/subscriptions/?customer={id}` and implement action buttons calling pause, resume, and edit endpoints.

### C. Invoices & Payments History
*   **Frontend Implementation:** In `CustomerProfileTab.tsx` (lines 65, 138–163, 735–791), invoice payments are mocked client-side.
*   **Backend Reality:** The `finance` app contains real `MonthlyBill` and `Transaction` models (routed at `/api/finance/monthly_bills/` and `/api/finance/transactions/`). It tracks actual delivery aggregations, payments received, and outstanding dues.
*   **Resolution Needed:** Connect the Payment History tab to a real API GET request calling `/api/finance/monthly_bills/?customer={id}`.

### D. Returnable Bottles & Containers
*   **Backend Reality:** The `inventory` app has detailed tracking models:
    *   `BottleType` (names, deposits).
    *   `CustomerBottleBalance` (Issued - Returned = Net Balance).
    *   `BottleTransaction` (records ISSUED, RETURNED, BROKEN, or REFILLED events, linked to orders and drivers).
*   **Frontend Reality:** The product page lists if an item is returnable, but there is no bottle management dashboard or audit screen in the frontend to track customer container balances or handle bottle returns.

---

## 3. Completely Missing Modules in Frontend

The following full-scale backend modules are running perfectly in the Django backend but have **no corresponding user interface in the React frontend app**:

### 1. Finance & Billing Panel (`finance` app)
*   **Backend Features:** 
    *   `MonthlyBillViewSet` (`/api/finance/monthly_bills/`).
    *   `trigger_generation` action for bulk invoice creation per calendar month.
    *   Automatic PDF invoice generation (`invoice_pdf` FileField).
*   **Missing Frontend UI:** A dedicated Billing tab or dashboard to view all unpaid monthly bills, record manual payments (creating `Transaction` objects), trigger monthly invoice batch generation, and download PDF bills.

### 2. HR, Attendance & Payroll Portal (`hr` app)
*   **Backend Features:**
    *   `EmployeeViewSet` with employee onboarding profiles and bulk creators.
    *   Compliance documents management (`EmployeeDocumentViewSet`) with admin verification triggers.
    *   Logistic readiness check-in & checkout tracking (`AttendanceViewSet`).
    *   Payroll manager (`MonthlyPayrollViewSet` with automated `generate` payroll service).
    *   Incentive rules for delivery benchmarks (e.g. `on_time_pct` > 95% = Rs. 500 bonus).
*   **Missing Frontend UI:** An Employee portal for admins to manage driver/staff lists, upload/verify Aadhaar/PAN cards, check daily attendance check-ins, configure bonus metrics, and process monthly payroll.

### 3. Taxation & GST Engine (`taxation` app)
*   **Backend Features:**
    *   `TaxRuleViewSet` (`/api/taxation/tax-rules/`) containing state-specific SGST, CGST, and IGST tax configurations.
    *   `ProductTaxCategoryViewSet` mapping items to HSN codes and categories (Essential vs. Standard vs. Exempt).
*   **Missing Frontend UI:** Settings panels to configure tax percentages per state, update product HSN codes, and generate GST tax reports.

### 4. Admin System Configurations (`administration` app)
*   **Backend Features:**
    *   `AdminConfiguration` singleton view containing tenant-wide parameters: `enable_delivery_photo` (forces photo proof on delivery), `require_signature` (forces customer signature on delivery), `auto_assign_orders`, and branding variables like `theme_color` and `company_name`.
*   **Missing Frontend UI:** A central System Settings page where administrators can toggle proof of delivery rules, auto-assignment, and customize system colors.

---

## 4. Recommended Future Roadmap & Additions

To take the Pench Dairy project from an admin prototype to an enterprise-grade delivery ERP, we recommend implementing the following modules and enhancements in future iterations:

### Phase 1: Real Database Integrations (High Priority)
*   **Replace Placebo Customer Discounts:** Link the customer discounts tab directly to `/api/inventory/customer-prices/`, allowing per-item discount controls.
*   **Expose Real Subscriptions:** Fetch actual customer subscriptions. Enable pausing, resume, and holiday skips from the UI.
*   **Expose Real Payment Invoices:** Replace the mock payments tab with actual monthly bills, allowing admins to mark invoices as paid.

### Phase 2: Core Admin Dashboard Additions (Medium Priority)
*   **Invoicing & Billing Dashboard:** Add a view to see global unpaid billing balances, download PDF invoices, and trigger monthly runs.
*   **Staff onboarding & Attendance Panel:** Expose driver onboarding, verification checklists (Aadhaar/PAN verification), and a check-in board showing who is logistically ready.
*   **GST Settings Page:** Enable SGST/CGST/IGST state tax configuring.

### Phase 3: Logistics & Field Enhancements (Innovation & Wow-Factor)
*   **GPS Route Replay Player:** The backend already collects historical location breadcrumbs in `DriverTrail`. Expand the tracking screen with a visual route replay slider, allowing admins to replay a driver's daily route on the map, speed it up, and pinpoint delays.
*   **Bottle Balance Audit Log:** Add a container ledger screen under each customer's details to log returns, container breakages, and deposits collected/refunded.
*   **Driver Mobile Companion App Integration:** Build out the companion application endpoints for the field staff to log real-time bottle collections, upload delivery proof photos (triggering the `enable_delivery_photo` setting), and capture customer signatures.
