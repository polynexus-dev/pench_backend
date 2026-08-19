# Privacy Policy for Pench Platform

**Effective Date:** August 19, 2026  
**Last Updated:** August 19, 2026  

---

## 1. Introduction

Welcome to **Pench** ("we," "our," "us," or "Platform"). Pench operates a multi-tenant logistics, recurring delivery, and ERP platform comprising the **Pench Backend Services**, **Pench Mobile Applications** (Customer & Driver apps), and **Pench Web Frontends**. 

This Privacy Policy explains how we collect, use, disclose, process, and safeguard your personal information when you use our websites, mobile applications, services, and software solutions (collectively, the "Services").

By registering, accessing, or using the Pench Platform, you consent to the practices described in this Privacy Policy. If you do not agree with the terms of this Privacy Policy, please do not access or use the Services.

---

## 2. Applicability & Covered Roles

This Privacy Policy applies to all users interacting with the Pench Platform across different roles:

1. **Customers / End-Users:** Individuals subscribing to or ordering daily essentials, dairy products, meal deliveries, or goods.
2. **Delivery Drivers / Agents:** Personnel conducting last-mile delivery operations using the Pench Driver Mobile Application.
3. **Merchants / Business Owners / Admins / Employees:** Enterprise users, tenant managers, and staff managing city operations, inventory, routes, and subscriptions via the ERP web dashboard.

---

## 3. Information We Collect

We collect information directly from you, automatically when you interact with our Services, and from third-party services as described below.

### 3.1. Information You Provide to Us

- **Account & Registration Data:** Full name, mobile phone number, email address, password/passcode, user role, and city/region.
- **Delivery & Address Information:** Street address, building/flat details, landmark, geo-coordinates (latitude and longitude), delivery instructions, and designated delivery zone.
- **Subscription & Order Details:** Daily or recurring delivery schedules, custom frequencies (e.g., daily, alternate days, weekdays), order history, product preferences, and vacation pause schedules.
- **Payment & Invoicing Information:** Transaction IDs, payment modes (UPI, credit/debit card, net banking, prepaid wallet balance), billing history, and tax/invoicing identifiers (processed securely via PCI-DSS compliant payment gateways).
- **Customer Support & Communications:** Feedback, support tickets, chat logs, and email or phone inquiries.

### 3.2. Information Collected Automatically

- **Real-Time GPS & Location Data:**
  - **For Delivery Drivers:** When active on a delivery trip, the Pench Driver app collects real-time foreground and background precise GPS coordinates (latitude, longitude, speed, and heading) to enable live route tracking, ETA estimation, path trail logging, and dispatch optimization.
  - **For Customers:** Device location (with consent) to pin delivery addresses accurately and verify service availability within operational city zones.
- **Proof of Delivery (POD) Media & Metadata:** Camera photos taken by drivers upon delivery completion, captured along with exact timestamp and geotagged GPS coordinates to confirm order fulfillment.
- **Device & Technical Data:** IP address, device identifier (IMEI, Android ID, or UUID), operating system version, browser type, hardware model, mobile network details, and push notification tokens (e.g., Firebase Cloud Messaging tokens).
- **Usage & Log Information:** Access times, app features used, pages viewed, API request logs, crash reports, and WebSocket connection logs.
- **Cookies & Session Tokens:** Session identifiers, authentication tokens (JWT), and preference cookies to maintain secure sessions and state across tenant subdomains.

---

## 4. How We Use Your Information

We use the collected information for legitimate business and operational purposes, including:

1. **Service Provision & Order Fulfillment:** Processing daily orders, recurring subscriptions, vacation pauses, and inventory adjustments across tenant schemas.
2. **Route Optimization & Driver Dispatch:** Utilizing location data with OR-Tools and OSRM routing engines to generate fuel-efficient delivery routes, sequence stops, and assign drivers to geographic zones.
3. **Real-Time Tracking & Proof of Delivery:** Displaying live delivery progress to admins and customers, calculating arrival estimates, and generating geotagged POD records.
4. **Billing & Financial Management:** Generating automated invoices, tracking payment statuses, adjusting prepaid wallet balances, and maintaining financial ledgers.
5. **Notifications & Alerts:** Sending transactional updates, OTP verifications, trip status alerts, bill reminders, and operational messages via SMS, WhatsApp, Push Notifications, and Email.
6. **Multi-Tenant Data Security:** Enforcing physical schema separation (e.g., public schema vs. city tenant schemas like Nagpur, Pune) to ensure data isolation across business entities.
7. **Platform Analytics & System Improvement:** Monitoring server performance, diagnosing software bugs, optimizing delivery density, and enhancing app user experience.
8. **Legal Compliance & Security:** Preventing fraud, unauthorized access, or misuse, and complying with applicable statutory, tax, and legal obligations.

---

## 5. Information Sharing and Disclosure

We respect your privacy and only share your personal data under the following circumstances:

### 5.1. Operational Sharing Within the Platform
- **Drivers:** Assigned drivers receive customer delivery names, address details, GPS pins, contact numbers for delivery coordination, and order items.
- **City Tenants & Admin Staff:** Authorized managers and administrators of a specific city tenant have access to customer profiles, orders, and delivery histories confined exclusively to their tenant schema.

### 5.2. Third-Party Service Providers
We share necessary data with trusted third-party service providers who assist in operating our Platform:
- **Routing & Mapping Services:** OpenStreetMap, OSRM, Nominatim, and Google Maps API for geocoding, driving distance matrices, and map rendering.
- **Communication & Notification Gateways:** SMS API providers (e.g., Twilio, MSG91), WhatsApp Business API, and Firebase Cloud Messaging (FCM) for push notifications.
- **Payment Processors:** PCI-DSS certified payment gateways (e.g., Razorpay, Stripe, Paytm, UPI providers) for payment processing.
- **Cloud Infrastructure & Hosting:** Secure cloud hosting, database management (PostgreSQL/PostGIS), and Redis caching services.

### 5.3. Legal and Regulatory Requirements
We may disclose your information if required to do so by law, court order, regulatory mandate, or governmental inquiry, or when we believe disclosure is necessary to protect the rights, property, safety, or security of Pench, our users, or the public.

### 5.4. Business Transfers
In the event of a merger, acquisition, corporate restructuring, asset sale, or bankruptcy, user data may be transferred as part of business assets, subject to confidentiality commitments.

---

## 6. Data Security & Storage

We employ industry-standard administrative, technical, and physical security measures to protect your personal information:
- **Multi-Tenant Database Isolation:** Tenant schemas physically isolate city data, preventing cross-tenant data exposure.
- **Encryption:** Encryption of sensitive data in transit using SSL/TLS protocols and secure token-based authentication (JWT/OAuth2). Passwords are protected using strong salted hashing algorithms (Argon2 / PBKDF2).
- **Access Controls:** Strict role-based access control (RBAC) ensuring employees and admins access only the data necessary for their role.
- **Background Location Security:** Driver GPS location streaming is restricted strictly to active trip durations and encrypted over Secure WebSockets (WSS).

---

## 7. Data Retention

We retain your personal data for as long as your account remains active or as required to fulfill the purposes outlined in this Privacy Policy:
- **Account & Subscription Data:** Retained for the lifetime of your account plus statutory periods required for legal and tax compliance.
- **Driver GPS Logs & POD Photos:** Retained for operational verification, dispute resolution, and audit trails for a maximum period necessary under business policies or applicable law.
- **Invoices & Financial Ledgers:** Retained as mandated by applicable financial, accounting, and GST tax regulations (typically 6-8 years).

When data is no longer required, it is securely deleted, anonymized, or destroyed.

---

## 8. Your Privacy Rights & Choices

Depending on your jurisdiction and role, you have the following rights regarding your personal data:

1. **Access & Update:** You can access and update your profile information, address, and delivery preferences through the account settings in the application.
2. **Subscription Control & Vacation Mode:** You can pause, modify, or cancel recurring subscriptions at any time via the customer app.
3. **App Permissions:** You can manage or revoke app permissions (Location access, Camera access, Push notifications) via your mobile device settings. Note that revoking essential permissions (such as Location or Camera for drivers) may impact app functionality.
4. **Account Deletion & Right to Eradication:** You may request the deletion of your account and personal data by contacting support. Data retention obligations imposed by law will apply.
5. **Marketing Preferences:** You can opt out of promotional communications at any time by following the unsubscribe instructions in those messages or updating your notification settings.

---

## 9. Children's Privacy

The Pench Platform is not directed to individuals under the age of 18 ("Children"). We do not knowingly collect personal information from children. If we become aware that a child has provided us with personal data without parental consent, we will take immediate steps to delete such information.

---

## 10. International & Regional Compliance

Pench complies with applicable data protection legislation, including:
- **Digital Personal Data Protection Act (DPDP Act, India) / IT Act 2000**
- General Data Protection Regulation (GDPR) standards where European data subjects are involved.
- California Consumer Privacy Act (CCPA) privacy standards for applicable users.

---

## 11. Changes to This Privacy Policy

We may update this Privacy Policy periodically to reflect changes in our practices, technology, or legal requirements. When updates occur, we will revise the "Last Updated" date at the top of this policy and notify users via app alerts, email, or a prominent notice on our website. Continued use of the Services after updates constitutes acceptance of the revised policy.

---

## 12. Contact Us & Grievance Officer

If you have questions, concerns, feedback, or requests regarding this Privacy Policy or our data practices, please contact our Data Protection & Grievance Officer at:

- **Entity Name:** Pench Logistics / Pench Food Technologies
- **Email:** privacy@pench.in / support@pench.in
- **Website:** https://pench.in
- **Grievance Officer:** Privacy & Compliance Team  
- **Address:** Pench Platform Headquarters, Operational Division, India

---
