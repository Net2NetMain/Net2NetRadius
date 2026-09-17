# Working architecture

## Deployment boundary

Every WISP owns an isolated installation, database, UISP connection, MikroTik credentials and hostname. There is no Net2Net cloud dependency. Nginx Proxy Manager terminates HTTPS for a WISP-specific hostname and proxies the web/API service. MikroTik NAS devices reach FreeRADIUS over internal OSPF loopbacks.

## Services

| Service | Responsibility |
| --- | --- |
| Web portal | Responsive Super Admin, WISP Admin and Client experiences |
| API | Business rules, sessions, audit log, branding and integrations |
| Worker | Five-minute UISP reconciliation, retention, backups and router health |
| PostgreSQL | Application data plus FreeRADIUS authentication/accounting tables |
| FreeRADIUS | PPPoE authentication, accounting and CoA/Disconnect |
| Redis | Short-lived jobs, locks, rate limiting and online-session cache |
| Speed test | Separate process beside the platform so tests cannot starve RADIUS |

## Key rules

1. UISP-to-PPPoE links require administrator confirmation before billing automation acts.
2. One UISP customer can own many PPPoE services. Customer suspension affects all linked services.
3. Suspended services remain authenticatable at `8k/8k`; restoration uses CoA and falls back to one disconnect.
4. Portal authentication accepts a PPPoE credential but never returns or displays stored credentials.
5. Packages separate advertised download/upload from provisioned download/upload.
6. Import preserves legacy rate limits exactly. Administrators can normalize package names later.
7. IP allocation is transactional and distinguishes private/local from public pools.
8. All administrative writes are audited.

## Delivery stages

1. Working application shell, database model and Windows/WSL bootstrap.
2. Authentication, account CRUD, packages, IP allocation and `.rsc` import preview.
3. FreeRADIUS PostgreSQL wiring, accounting and safe migration tests.
4. MikroTik RouterOS API, multi-NAS health and CoA.
5. UISP mapping, five-minute reconciliation and suspension workflow.
6. Client portal, statements and connection history.
7. Core-hosted speed test and diagnostic reporting.
8. Backup/retention, production hardening and Unraid containers/templates.

