# Multi-Company Architecture Guide

The Pench ERP backend is designed to support multiple companies operating across multiple cities, while maintaining strict data isolation. This is achieved using PostgreSQL schemas via the `django-tenants` library.

## Core Concepts

1. **Company (Public Entity)**
   - A `Company` is a logical grouping that exists in the **public schema**.
   - It serves as an umbrella for one or more cities.
   - Example: "Aniket Corp", "Pench Foods".

2. **City (The Tenant / Schema)**
   - The `City` model is the actual **Tenant Model**.
   - Every `City` record created generates a completely isolated database schema in PostgreSQL.
   - All operational data (Orders, Customers, Drivers, HR) lives *inside* a City schema.
   - A `City` belongs to a `Company` via a Foreign Key.

3. **Domain (Routing)**
   - Every `City` has a `Domain`.
   - The backend uses the domain of the incoming HTTP request to determine which City schema to route the data to.

## Example Scenario: Same City, Multiple Companies

Suppose both **Pench Foods** and **Aniket Corp** operate in **Nagpur**. Because they are separate companies, their customer and order data must never mix. 

Here is how you configure this in the Django Admin:

### 1. Create the Companies (Public Schema)
- **Company 1:** Name: `Pench Foods`, Code: `PENCH`
- **Company 2:** Name: `Aniket Corp`, Code: `ANIKET`

### 2. Create the Cities (Tenant Schemas)
Because `City` is the schema, you create *two* Nagpur records, one for each company. The `code` is unique per company, so both can use `NGP`.

> [!WARNING]
> **Schema Name Uniqueness Requirement**
> The `schema_name` field maps directly to a PostgreSQL schema. Therefore, **the `schema_name` MUST be globally unique across the entire database.** Even if two cities share the same name (e.g., "Nagpur"), their schema names must be distinct (e.g., `pench_nagpur` and `aniket_nagpur`). Failure to use a unique schema name will result in a database error.

- **City A (Pench's Nagpur)**
  - Name: `Nagpur`
  - Code: `NGP`
  - Company: `Pench Foods`
  - Schema Name: `pench_nagpur`
  - Domain: `nagpur.pench.com`

- **City B (Aniket's Nagpur)**
  - Name: `Nagpur`
  - Code: `NGP`
  - Company: `Aniket Corp`
  - Schema Name: `aniket_nagpur`
  - Domain: `nagpur.aniket.com`

### 3. How the Frontend Works

If Aniket Corp's main website is `aniket.com`, the user visits it and sees a login page.

1. **Fetch Companies:** The frontend makes a GET request to `api.pench.com/api/erp/tenants/companies/`.
2. **Select Scope:** The user selects "Aniket Corp" and then "Nagpur".
3. **Redirect:** The frontend redirects the user to `nagpur.aniket.com`.
4. **Data Isolation:** All subsequent API calls from `nagpur.aniket.com` are automatically routed by the backend to the `aniket_nagpur` PostgreSQL schema. 

## API Integration

The Public API endpoint for frontend discovery is:
`GET /api/erp/tenants/companies/`

**Response Example:**
```json
[
    {
        "id": 1,
        "name": "Aniket Corp",
        "code": "ANIKET",
        "is_active": true,
        "cities": [
            {
                "id": 2,
                "name": "Nagpur",
                "schema_name": "aniket_nagpur",
                "code": "NGP",
                "is_active": true
            }
        ]
    }
]
```

## Summary
- **Never share a City across companies** if data must be isolated.
- Create a new `City` (Tenant) for every location a Company operates in.
- The frontend dynamically determines the API URL (domain) based on the City the user selects.
