# Google Play Console - App Access Test Credentials

**Project:** Pench Platform (Customer & Driver Mobile Apps)  
**Environment:** Live VM Server (`https://pench-nagpur.pench.api.polynexus.in`)  
**Date Created:** August 19, 2026  

---

## 1. Overview for Google Play Console Submission

When submitting the **Pench Customer App** or **Pench Driver App** for review under **Google Play Console -> App Content -> App Access**, select **"All or some functionality is restricted"** and enter the credentials and instructions below.

---

## 2. Test Account Credentials

| Account Role | Username | Phone Number | Password | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Customer App** | `google_test_customer` | `9999000001` | `GoogleTest@2026` | Customer account for placing orders, daily subscriptions, and viewing delivery schedules |
| **Driver App** | `google_test_driver` | `9999000002` | `GoogleTest@2026` | Delivery driver account for trip management, active routes, and proof-of-delivery (POD) photo submission |
| **Admin / ERP Dashboard** | `google_test_admin` | `9999000003` | `GoogleTest@2026` | SuperAdmin / Manager account for backend control and route dispatch testing |

> **Note on OTP Authentication:**  
> If logging in via Phone Number OTP, enter phone `9999000001` or `9999000002`. The API returns the OTP code in the response payload for testing/review environments.

---

## 3. Step-by-Step Instructions for Google App Reviewers

### A. Testing the Customer Mobile App
1. Open the **Pench Customer App**.
2. Select Login via Username or Mobile Number:
   - **Username:** `google_test_customer`
   - **Password:** `GoogleTest@2026`  
   *(Or enter Phone Number `9999000001` to request OTP).*
3. Upon logging in, the reviewer can:
   - Browse the daily products catalog (A2 Milk, Paneer, etc.).
   - Create or manage recurring subscriptions (Daily, Alternate Days, Custom).
   - View scheduled orders and active wallet balances.
   - Test address management and delivery notifications.

### B. Testing the Driver Mobile App
1. Open the **Pench Driver App**.
2. Log in using Driver credentials:
   - **Username:** `google_test_driver`
   - **Password:** `GoogleTest@2026`
3. Upon logging in, the reviewer can:
   - View assigned delivery trips and optimized stop sequences.
   - Start a delivery trip and view interactive GPS route maps.
   - Complete deliveries by uploading Proof of Delivery (POD) photos and updating order status.

---

## 4. Verification Status

- **Database Registration:** Active & Verified on Live VM Environment.
- **Authentication API Status:** Tested & Responding with `HTTP 200 OK`.
