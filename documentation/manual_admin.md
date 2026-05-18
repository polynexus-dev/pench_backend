# Project Manual: Admin

Welcome to the Pench ERP Administration Manual. This guide explains how to manage your city/tenant and configure system behavior.

## 1. Dashboard Overview
The Admin dashboard provides a summary of:
- Active orders for the day.
- Driver statuses (On-duty vs. Off-duty).
- Critical inventory levels.

## 2. Configuration Settings
Navigate to **Administration -> Admin Configuration** to manage:
- **Enable Delivery Photo**: If on, drivers MUST upload a photo to complete delivery.
- **Auto-Assign Orders**: Automatically assigns orders to drivers based on historical routes.
- **Max Cancellation Time**: Minutes before delivery start when customers can no longer cancel.
- **Theme Customization**: Update your company name and primary theme color.

## 3. User & Identity Management
All users are managed under **User Management** in the Public Schema:
- **Global Identity**: Admins, Drivers, and Customers are centrally stored.
- **Automated Roles**: Groups (SuperAdmin, Manager, Driver, Customer) are initialized automatically.
- **Permissions**: Use Django Groups for RBAC (Role Based Access Control).

## 4. Developer Tools
- **API Documentation**: A role-based Postman collection (v4.2.1) is available in the `documentation/` folder for system integration.
- **Token Monitoring**: All API responses include `expires_in_seconds` for session tracking.

## 5. Route Optimization
To create a route:
1. Go to **Logistics -> Optimized Routes**.
2. Select the delivery date and the orders to include.
3. Click "Generate Optimized Route".
4. Assign a driver to the route.

## 6. Inventory Control
- **Products**: Add new products and set categories.
- **Bottle Tracking**: Monitor "Issued" vs. "Returned" bottles for each customer to ensure asset recovery.

## 7. Live Tracking & Reconnection Resiliency
The real-time vehicle and driver tracking dashboard features advanced state restoration and connectivity buffering:
- **Zero-Loss Tracking**: If a driver's mobile app or the admin's tracking browser suffers a temporary network disconnection, the system automatically keeps previous trail segments stored in the database.
- **Auto-Restoration**: As soon as connection is re-established, the backend pushes the entire active day's trail instantly. The map recovers and updates immediately, preventing any trail data from being wiped or showing up as blank.
- **Live Diagnostics**: The dashboard shows a real-time connection status light (`Live Connected` vs `Disconnected`) so admins always know they are seeing up-to-the-second data.
