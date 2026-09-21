# 🛠️ Pench ERP: Complete Project Setup Guide (From Scratch)

This guide walks you through setting up the entire **Pench Logistics ERP** system on your local machine (Windows / macOS / Linux).

---

## 📋 System Prerequisites

Before starting, ensure you have the following installed:

| Component | Minimum Version | Notes |
| :--- | :--- | :--- |
| **Python** | `3.11` to `3.13` (64-bit) | Ensure `python` and `pip` are added to your system `PATH`. |
| **PostgreSQL** | `15+` | Must include the **PostGIS** geospatial extension. |
| **Redis** | `6+` | Used for Django Caching, Channel Layers (WebSockets), and Celery Broker. |
| **GDAL / GEOS** | `3.6+` | C++ geospatial library required by GeoDjango. (Precompiled `.whl` provided for Windows). |

---

## 🚀 Step 1: Virtual Environment & Python Packages

1. Open PowerShell / Terminal in the project root directory:
   ```powershell
   cd c:\Users\admin\Desktop\tejas\Pench
   ```

2. Create and activate a Python virtual environment:
   ```powershell
   python -m venv myenv
   .\myenv\Scripts\Activate.ps1
   ```
   *(On Linux/macOS: `source myenv/bin/activate`)*

3. Navigate to the backend folder:
   ```powershell
   cd pench_backend
   ```

4. Install the core Python dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

5. Install the GDAL binary wheel:
   - **On Windows (Python 3.13)**:
     ```powershell
     pip install "gdal-3.10.2-cp313-cp313-win_amd64.whl"
     ```
   - **On Ubuntu / Debian**:
     ```bash
     sudo apt-get update && sudo apt-get install -y binutils libproj-dev gdal-bin libgdal-dev
     ```

---

## ⚙️ Step 2: Environment Configuration (`.env`)

1. Copy `.env.example` to `.env` inside `pench_backend/`:
   ```powershell
   Copy-Item .env.example .env
   ```

2. Open `pench_backend/.env` and verify your credentials:
   ```ini
   SECRET_KEY=your-secure-secret-key-replace-this-in-production
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1,.localhost,nagpur.localhost,pune.localhost,*

   # PostgreSQL + PostGIS Database
   DB_NAME=pench_foods
   DB_USER=postgres
   DB_PASSWORD=admin
   DB_HOST=localhost
   DB_PORT=5432

   # Redis (Celery Broker & Django Cache)
   REDIS_URL=redis://127.0.0.1:6379/0
   CACHE_REDIS_URL=redis://127.0.0.1:6379/1

   # OSRM Driving Distance Engine
   OSRM_BASE_URL=http://router.project-osrm.org

   # Default Depot Geolocation (Nagpur / Mumbai)
   DEPOT_LAT=21.1458
   DEPOT_LNG=79.0882
   ```

---

## 🗄️ Step 3: Database & PostGIS Setup

You can either run the automated database helper or configure it manually:

### Option A: Automated Script (Recommended)
Run the built-in database creation script:
```powershell
python create_database.py
```
*This checks for PostgreSQL, creates the `pench_foods` database if missing, and executes `CREATE EXTENSION IF NOT EXISTS postgis;`.*

### Option B: Manual PostgreSQL CLI (`psql`)
```sql
CREATE DATABASE pench_foods;
\c pench_foods;
CREATE EXTENSION postgis;
```

---

## 🧬 Step 4: Multi-Tenant Schema Migrations

Because Pench ERP uses **`django-tenants`** (separate PostgreSQL schema per city), you must run migrations using `migrate_schemas`:

1. Run shared/public schema migrations first:
   ```powershell
   python manage.py migrate_schemas --shared
   ```

2. Verify all models and app checks:
   ```powershell
   python manage.py check
   ```

---

## 🏢 Step 5: System Initialization (Public Tenant, City Schemas & SuperAdmin)

Execute the automated system initializer:
```powershell
python initialize_system.py
```

### What this script sets up automatically:
- **Corporate Company**: Creates `polynexus` / `Pench Foods Pvt Ltd`.
- **Public Tenant**: Creates the `public` schema tenant and binds domains:
  - `localhost`
  - `127.0.0.1`
- **City Tenants (Operational Schemas)**:
  - `nagpur` (`nagpur.localhost`)
  - `pune` (`pune.localhost`)
  - Automatically runs tenant-specific migrations across all created city schemas!
- **Default SuperAdmin Account**:
  - **Username**: `admin`
  - **Password**: `admin`
  - **Role**: `SuperAdmin` (Full ERP & Admin privileges)

---

## 🌐 Step 6: Local Hosts File Configuration (Multi-Tenancy)

To route requests accurately to tenant subdomains on your local development machine:

1. Open **Notepad** as **Administrator**.
2. Open file: `C:\Windows\System32\drivers\etc\hosts`.
3. Add the following lines:
   ```text
   127.0.0.1 localhost
   127.0.0.1 nagpur.localhost
   127.0.0.1 pune.localhost
   ```
4. Save and close the file.

---

## 📦 Step 7: Seed Initial Operational / Demo Data (Optional)

To seed initial warehouses, products, bottle deposits, and demo customer GPS coordinates in the `pune` or `nagpur` schema:
```powershell
python create_dummy_data.py
```

---

## 🏃 Step 8: Running the Services

To run the full Pench ERP platform with real-time WebSockets, background route solving, and cron dispatching, start these processes:

### Terminal 1: Django ASGI & HTTP Server (Daphne / Runserver)
```powershell
cd c:\Users\admin\Desktop\tejas\Pench\pench_backend
.\..\myenv\Scripts\Activate.ps1
python manage.py runserver 8000
```
*Access point: `http://localhost:8000` (Public) & `http://nagpur.localhost:8000` (Nagpur Tenant)*

### Terminal 2: Redis Server
Ensure Redis service is active:
```powershell
redis-server
```
*(Or via Docker: `docker run -d --name pench-redis -p 6379:6379 redis:alpine`)*

### Terminal 3: Celery Worker (AI Route Optimization & Background Tasks)
On Windows, use `-P solo` or `gevent` because standard process forking is not supported:
```powershell
cd c:\Users\admin\Desktop\tejas\Pench\pench_backend
.\..\myenv\Scripts\Activate.ps1
celery -A config worker -l info -P solo
```

### Terminal 4: Celery Beat (Scheduled Recurring Crons)
```powershell
cd c:\Users\admin\Desktop\tejas\Pench\pench_backend
.\..\myenv\Scripts\Activate.ps1
celery -A config beat -l info
```

---

## 🧪 Step 9: Testing & Verification

1. **Django Admin Interface**:
   - URL: `http://localhost:8000/admin/`
   - Login: `admin` / `admin`
2. **Tenant API Login**:
   - URL: `http://nagpur.localhost:8000/api/accounts/login/`
   - Credentials: `admin` / `admin`
3. **Postman Testing**:
   - Open Postman.
   - Import: `postman_collection (4).json`.
   - Import Environment: `pench_backend/documentation/Local_Env.postman_environment.json`.
   - Follow the step-by-step workflow detailed in [API_FLOW_STEP_BY_STEP.md](file:///c:/Users/admin/Desktop/tejas/Pench/API_FLOW_STEP_BY_STEP.md).
