# Net2Net Local RADIUS Manager

Standalone, per-WISP RADIUS management software for MikroTik PPPoE networks. It replaces MikroTik User Manager, integrates with the WISP's local UISP CRM, and provides branded portals for Net2Net, WISP staff, and customers.

## Current milestone

The first working scaffold includes:

- FastAPI service with health, bootstrap, dashboard, package, subscriber, router and IP-pool endpoints
- PostgreSQL-first schema designed to coexist with the standard FreeRADIUS SQL tables
- React/Vite web dashboard with permanent Net2Net sub-branding
- Windows + WSL2 bootstrap scripts (no Docker)
- Explicit boundaries for UISP sync, MikroTik API, CoA and User Manager import work

## Docker / Unraid beta

The container runs the web portal, management API and RADIUS authentication/accounting service in one local WISP appliance. It persists all operational data under `/data`.

Ports:

- `8080/tcp` — administrator and client portal
- `1812/udp` — RADIUS authentication
- `1813/udp` — RADIUS accounting

Before starting a production container, set unique values for `APP_SECRET` (32+ characters), `BOOTSTRAP_SUPERADMIN_PASSWORD`, `BOOTSTRAP_WISPADMIN_PASSWORD`, and `RADIUS_SHARED_SECRET`. The initial administrator passwords are used only if the database is empty. Include the mapped `/data` directory in the Unraid backup schedule.

For a local Docker test:

```powershell
Copy-Item .env.example .env
# Replace every secret in .env first.
docker compose up --build
```

Open `http://SERVER-IP:8080`. The manual Unraid import template is [unraid/net2net-local-radius.xml](unraid/net2net-local-radius.xml). It is intentionally a beta template until an image registry and final public repository URL are selected.

The Super Admin can create and download consistent SQLite backups through the protected `/api/system/backups` endpoint. The container retains the latest 14 backups by default.

## Run the development build

### Web interface

```powershell
cd apps/web
npm install
npm run dev
```

Open `http://localhost:5173`.

### API (Windows preview)

```powershell
cd apps/api
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item ..\..\.env.example ..\..\.env
uvicorn app.main:app --reload --port 8000
```

The API uses in-memory preview data until `DATABASE_URL` is connected in the next milestone. Open `http://localhost:8000/docs`.

### WSL2 services

Run PowerShell as Administrator:

```powershell
.\scripts\install-windows.ps1
```

The installer enables WSL2/Ubuntu when needed and then installs PostgreSQL, FreeRADIUS, its PostgreSQL driver, Redis, Python and supporting tools inside Ubuntu. It intentionally does not alter any MikroTik router.

## Operating model

- One isolated installation per WISP
- WISP-specific branding with permanent "Powered by Net2Net Local RADIUS Manager"
- UISP is the CRM and billing source of truth
- A confirmed UISP customer can own multiple PPPoE services
- UISP suspension throttles every linked PPPoE service to `8k/8k`
- Packages show advertised rates while storing separate provisioned rates (for example 5/5 displayed, 6/6 provisioned)
- Private and public address pools allocate the next available address
- Routers are registered manually by OSPF loopback IP and use the internal RouterOS API

See [docs/architecture.md](docs/architecture.md) for the working architecture and delivery stages.
