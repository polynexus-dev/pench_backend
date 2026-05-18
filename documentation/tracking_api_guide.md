# Pench Logistics - Real-Time Tracking API Guide

This document provides the necessary URLs, headers, and payload structures for Mobile and Frontend developers to integrate with the Real-Time WebSocket Tracking Service.

---

## 1. Core Concepts

*   **Protocol:** WebSockets (`ws://` for local, `wss://` for production)
*   **Authentication:** JWT (JSON Web Tokens). WebSockets cannot easily send standard HTTP headers like `Authorization: Bearer <token>`, so the token must be passed in the URL Query String.
*   **Tenant Routing:** The backend uses multi-tenancy. The WebSocket connection *must* use the tenant's specific subdomain (e.g., `pune.pench.in` or `nagpur.pench.in`) as the Host. The backend automatically routes data to the correct city database based on this URL.

---

## 2. Authentication (REST API)

Before connecting to the WebSocket, both Mobile Drivers and Frontend Admins must obtain an Access Token via the standard HTTP login endpoint.

**Endpoint:** `POST /api/accounts/login/`
**Base URL:** `https://<tenant_subdomain>.pench.in` (e.g., `https://pune.pench.in`)
**Headers:** `Content-Type: application/json`
**Body:**
```json
{
    "username": "driver_nagpur",
    "password": "your_password"
}
```
**Response:**
```json
{
    "access": "eyJhbGciOiJIUzI1NiIsInR5c...",
    "refresh": "eyJhbGciOiJIUzI1NiIsInR5c..."
}
```
*(Store the `access` token for the WebSocket connection).*

---

## 3. Mobile Developer Guide (Sending Locations)

The mobile app should connect to the WebSocket and stream GPS coordinates. The backend will automatically save these to the database and generate breadcrumb trails.

### WebSocket Connection URL
```text
wss://<tenant_subdomain>.pench.in/ws/tracking/?token=<YOUR_ACCESS_TOKEN>
```
*Example:* `wss://pune.pench.in/ws/tracking/?token=eyJhbGci...`

### Sending Location Payload
Once connected, send a JSON stringified object containing the latitude and longitude.

**Frequency:** Recommend sending every 3 to 5 seconds while a trip is active.
**JSON Payload Structure:**
```json
{
    "lat": 18.520430,
    "lng": 73.856743
}
```

### Mobile Connection Best Practices
1.  **Auto-Reconnect:** WebSockets drop on mobile networks (tunnels, switching from WiFi to 4G). The mobile app MUST implement a reconnection loop with exponential backoff.
2.  **Background Execution:** Location tracking usually requires background permissions on Android/iOS to keep the socket alive while the screen is off.
3.  **Token Expiry:** If the WebSocket disconnects and the JWT token has expired, the app must call the `/api/accounts/login/refresh/` endpoint to get a new token before attempting to reconnect.

---

## 4. Frontend/Admin Developer Guide (Receiving Locations & State Restoration)

The web dashboard connects to the *exact same* WebSocket endpoint. If the user connecting has Admin/Staff privileges, the backend will automatically recognize them as a "viewer", subscribe them to driver updates, and synchronize them with existing states.

### WebSocket Connection URL
```text
wss://<tenant_subdomain>.pench.in/ws/tracking/?token=<YOUR_ADMIN_ACCESS_TOKEN>
```

### Initial State Synchronization (State Restoration on Connect/Reconnect)
Upon a successful WebSocket connection, the backend will immediately fetch and send a snapshot of all active drivers and their historical trails from the last 12 hours. This ensures that the map is populated immediately upon load or reconnection without waiting for new GPS coordinates.

**Initial State JSON Message Structure:**
```json
{
    "type": "initial_state",
    "drivers": [
        {
            "driver_id": "45f24a92-0e27-4fd3-bac8-7064e96508dd",
            "driver_name": "Ramesh Driver",
            "lat": 18.517458,
            "lng": 73.818031,
            "trail": [
                [73.817691, 18.516941],
                [73.817928, 18.517102],
                [73.818031, 18.517458]
            ]
        }
    ]
}
```
*Frontend Action:* Listen for `type === "initial_state"`, iterate through `drivers`, and call your map drawing/marker update functions for each driver to draw the initial markers and trails.

### Receiving Live Broadcasts
Listen for incoming messages on the WebSocket. The backend will broadcast a payload every time a driver updates their location.

**Incoming Message Structure:**
```json
{
    "type": "broadcast_location",
    "driver_id": "45f24a92-0e27-4fd3-bac8-7064e96508dd",
    "driver_name": "Ramesh Driver",
    "lat": 18.517458,
    "lng": 73.818031,
    "trail": [
        [73.817691, 18.516941],
        [73.817928, 18.517102],
        [73.818031, 18.517458]
    ]
}
```

### Payload Details for Frontend Map Rendering:
*   `lat`, `lng`: The current live location of the driver. Use this to move the marker `L.marker([lat, lng])`.
*   `trail`: An array of historical coordinates for the current day. 
    *   **CRITICAL FORMATTING NOTE:** GeoJSON standard stores coordinates as `[Longitude, Latitude]`. The `trail` array returns them exactly like this. If you are using Leaflet.js or Google Maps, you must flip them to `[Latitude, Longitude]` before drawing your Polyline.
    *   *Notice:* On reconnection, the `initial_state` message sends the complete sequence of past positions in this exact format. You can pass the updated array straight to your polyline update method to draw a seamless snapped path.

---

## 5. Local Development Testing

If frontend or mobile developers are testing against a local backend, they must use specific URLs to ensure the Multi-Tenant middleware resolves the schemas correctly:

*   **Do NOT use:** `ws://localhost:8000/ws/tracking/` (This points to the Public schema, which will reject tracking data).
*   **USE:** `ws://127.0.0.1:8000/ws/tracking/` (Mapped to Pune schema) OR `ws://nagpur.localhost:8000/ws/tracking/` (Mapped to Nagpur schema).

*(Ensure the backend is running via `daphne` or `runserver` before connecting).*
