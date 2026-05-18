# Live Tracking Testing Guide

This document explains how to test the real-time location tracking system using WebSockets (Django Channels) in both local and VM environments.

---

## 1. Local System Testing
Local testing uses the built-in simulation tools to mock a mobile driver and an admin dashboard.

### Prerequisites
- **Python Libraries**: Ensure `websockets`, `requests`, and `django-channels` are installed.
- **Local Server**: Running on `127.0.0.1:8083`.
- **CORS**: `CORS_ALLOW_ALL_ORIGINS = True` must be set in `config/local_settings.py`.

### Steps
1.  **Serve the Dashboard**:
    Open a terminal in the root folder and run:
    ```bash
    python -m http.server 8000
    ```
2.  **Open the Viewer**:
    Go to `http://localhost:8000/tracking_viewer.html` in your browser.
3.  **Connect to Backend**:
    - **Host**: `localhost:8083` (or `pune.localhost:8083` if DNS is set).
    - **Credentials**: Use an **Admin/Staff** account.
    - Click **Start Tracking**.
4.  **Run Simulator**:
    Open a new terminal and run:
    ```bash
    python simulate_tracking.py
    ```
    *Note: The script should use a valid driver username like `driver_nagpur`.*

---

## 2. VM / Production Testing
Testing on a VM requires ensuring that the WebSockets can traverse firewalls and that the domain/tenant mapping is correct.

### Prerequisites
- **Redis**: Required for VM/Production (the local `InMemoryChannelLayer` will not work across processes).
- **ASGI Server**: Use `daphne` or `gunicorn` with a worker class (Uvicorn).
- **Nginx/Proxy**: Must be configured to handle WebSocket upgrades:
  ```nginx
  location /ws/ {
      proxy_pass http://127.0.0.1:8083;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header Host $host;
  }
  ```

### Steps
1.  **Configure Hosts**:
    On the machine where you run the simulator/browser, ensure the VM's IP is mapped to your tenant domain (e.g., `pune.pench-erp.com`).
2.  **Update Simulator**:
    In `simulate_tracking.py`, update the `BASE_URL` and `WS_URL` to point to the VM domain or public IP.
3.  **Check Firewall**:
    Ensure port `80` (HTTP) or `8083` (if direct) is open for both TCP and WebSocket connections.
4.  **Protocol**:
    If using HTTPS on the VM, use `wss://` instead of `ws://` in the dashboard and simulation script.

---

## 3. Common Issues & Troubleshooting

### Login 404 Error
- **Cause**: The `TenantMiddleware` cannot find a matching domain for the request.
- **Fix**: Ensure the hostname you are using (e.g., `pune.localhost`) exists in the `tenants.Domain` table for the correct schema.

### Database Error: "relation tracking_driverlocation does not exist"
- **Cause**: Saving tracking data to the `public` schema instead of a tenant schema.
- **Fix**: Use a tenant-specific domain (e.g., `nagpur.localhost`) instead of `localhost`.

### Dashboard says "Disconnected"
- **Cause**: WebSocket connection failed (CORS or network).
- **Fix**: Check the browser's **Developer Tools (F12) > Console** for specific error messages. Ensure the `JWT Token` is valid and the user is `is_staff=True`.

### Coordinates not updating
- **Cause**: Simulation script is disconnected or pointing to the wrong URL.
- **Fix**: Check the simulation terminal for `[>] Sending Location` logs.
