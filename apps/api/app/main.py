import hmac
import json
import logging
import os
import re
import signal
import sqlite3
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
from typing import Annotated

import routeros_api
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .auth import COOKIE_NAME, create_token, current_identity, hash_password, verify_password
from .config import get_settings
from .database import SessionDep, create_db, engine
from .models import (
    AccountingSession,
    AppUser,
    AppUserCreate,
    AppUserRead,
    IpPool,
    IpPoolCreate,
    IpPoolRead,
    IpPoolUpdate,
    Package,
    PackageCreate,
    PackageRead,
    PackageUpdate,
    Role,
    Status,
    Router,
    RouterCreate,
    RouterRead,
    RouterUpdate,
    SpeedTest,
    Subscriber,
    SubscriberCreate,
    SubscriberRead,
    SubscriberStatusUpdate,
    SubscriberUpdate,
    MikrotikUserManagerImport,
)
from .mikrotik_import import parse_user_manager_export, split_rate
from .freeradius_sync import sync as sync_freeradius
from .routeros import (
    disconnect_subscriber,
    enforce_one_pppoe_session_per_host,
    inspect_router,
    live_pppoe_traffic,
)
from .security import decrypt_secret, encrypt_secret
from .uisp import test_connection as test_uisp_connection

settings = get_settings()
logger = logging.getLogger(__name__)
CurrentIdentity = Annotated[dict, Depends(current_identity)]
BRANDING_FILE = Path(settings.data_dir) / "branding.json"
LOGO_FILE = Path(settings.data_dir) / "wisp-logo"


def require_admin(identity: CurrentIdentity) -> dict:
    if identity["role"] not in (Role.SUPER_ADMIN.value, Role.WISP_ADMIN.value):
        raise HTTPException(403, "Administrator login required")
    return identity


AdminIdentity = Annotated[dict, Depends(require_admin)]


def require_superadmin(identity: CurrentIdentity) -> dict:
    if identity["role"] != Role.SUPER_ADMIN.value:
        raise HTTPException(403, "Super Admin login required")
    return identity


SuperAdminIdentity = Annotated[dict, Depends(require_superadmin)]


def sqlite_database_path() -> Path | None:
    if not settings.database_url.startswith("sqlite:///"):
        return None
    return Path(settings.database_url.removeprefix("sqlite:///"))


def is_lab(value) -> bool:
    return str(getattr(value, "username", "")).startswith("lab-test@") or str(
        getattr(value, "site_name", "")
    ).lower() == "home lab"


def visible(values):
    return list(values) if settings.show_lab_data else [value for value in values if not is_lab(value)]


def bootstrap_db():
    create_db()
    with Session(engine) as session:
        if not session.exec(select(Package)).first():
            session.add_all(
                [
                    Package(
                        name="5/5 Mbps",
                        advertised_down_mbps=5,
                        advertised_up_mbps=5,
                        provisioned_down_mbps=6,
                        provisioned_up_mbps=6,
                    ),
                    Package(
                        name="10/10 Mbps",
                        advertised_down_mbps=10,
                        advertised_up_mbps=10,
                        provisioned_down_mbps=11,
                        provisioned_up_mbps=11,
                    ),
                    Package(
                        name="20/20 Mbps",
                        advertised_down_mbps=20,
                        advertised_up_mbps=20,
                        provisioned_down_mbps=21,
                        provisioned_up_mbps=21,
                    ),
                ]
            )
            session.commit()
        if not session.exec(select(IpPool)).first():
            session.add(IpPool(name="Local subscribers", kind="private", start_address="10.250.0.10", end_address="10.250.0.250"))
            session.commit()
        if not session.exec(select(AppUser)).first():
            session.add_all(
                [
                    AppUser(
                        username=settings.bootstrap_superadmin_username,
                        display_name="Net2Net Super Admin",
                        role=Role.SUPER_ADMIN,
                        password_hash=hash_password(settings.bootstrap_superadmin_password),
                    ),
                    AppUser(
                        username=settings.bootstrap_wispadmin_username,
                        display_name="WISP Administrator",
                        role=Role.WISP_ADMIN,
                        password_hash=hash_password(settings.bootstrap_wispadmin_password),
                    ),
                ]
            )
            session.commit()


settings.validate_production()
bootstrap_db()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_production()
    bootstrap_db()
    yield


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "environment": settings.app_env}


@app.get("/api/system/status")
def system_status(_: SuperAdminIdentity):
    database_path = sqlite_database_path()
    return {
        "environment": settings.app_env,
        "database": "sqlite" if database_path else "postgresql",
        "data_dir": str(Path(settings.data_dir).resolve()),
        "database_size_bytes": database_path.stat().st_size if database_path and database_path.exists() else 0,
        "backup_count": len(list((Path(settings.data_dir) / "backups").glob("*.db"))),
    }


@app.get("/api/uisp/status")
def uisp_status(_: AdminIdentity):
    return test_uisp_connection()


@app.post("/api/system/backups")
def create_backup(_: SuperAdminIdentity):
    source = sqlite_database_path()
    if not source or not source.exists():
        raise HTTPException(501, "In-app backup is currently available for SQLite deployments only")
    backup_dir = Path(settings.data_dir) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"net2net-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.db"
    with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
        source_db.backup(target_db)
    backups = sorted(backup_dir.glob("*.db"), key=lambda file: file.stat().st_mtime, reverse=True)
    for old in backups[settings.backup_max_count:]:
        old.unlink()
    return {"filename": target.name, "size_bytes": target.stat().st_size}


@app.get("/api/system/backups/{filename}")
def download_backup(filename: str, _: SuperAdminIdentity):
    if Path(filename).name != filename or not filename.endswith(".db"):
        raise HTTPException(400, "Invalid backup name")
    backup = Path(settings.data_dir) / "backups" / filename
    if not backup.exists():
        raise HTTPException(404, "Backup not found")
    return FileResponse(backup, filename=filename, media_type="application/octet-stream")


@app.post("/api/auth/login")
def login(data: dict, response: Response, session: SessionDep):
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    user = session.exec(select(AppUser).where(AppUser.username == username)).first()
    if user and user.enabled and verify_password(password, user.password_hash):
        identity = {"username": user.username, "display_name": user.display_name, "role": user.role.value}
    else:
        subscriber = session.exec(select(Subscriber).where(Subscriber.username == username)).first()
        if not subscriber or subscriber.status == "disabled" or not hmac.compare_digest(
            password, decrypt_secret(subscriber.password_ciphertext)
        ):
            raise HTTPException(401, "Incorrect username or password")
        identity = {"username": subscriber.username, "display_name": subscriber.display_name, "role": Role.CLIENT.value}
    response.set_cookie(
        COOKIE_NAME,
        create_token(identity["username"], identity["role"], identity["display_name"]),
        httponly=True,
        samesite="strict",
        secure=settings.app_env != "development",
        max_age=12 * 60 * 60,
    )
    return identity


@app.get("/api/auth/me")
def me(identity: CurrentIdentity):
    return {
        "username": identity["sub"],
        "display_name": identity["name"],
        "role": identity["role"],
    }


@app.get("/api/admin/users", response_model=list[AppUserRead])
def list_admin_users(session: SessionDep, _: SuperAdminIdentity):
    """Only Super Admins can view or create WISP Administrator accounts."""
    return session.exec(select(AppUser).order_by(AppUser.display_name)).all()


@app.post("/api/admin/users", response_model=AppUserRead, status_code=201)
def create_wisp_admin(data: AppUserCreate, session: SessionDep, _: SuperAdminIdentity):
    username = data.username.strip()
    if session.exec(select(AppUser).where(AppUser.username == username)).first():
        raise HTTPException(409, "That portal username is already in use")
    user = AppUser(
        username=username,
        display_name=data.display_name.strip(),
        role=Role.WISP_ADMIN,
        password_hash=hash_password(data.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@app.post("/api/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)


def live_session_for_subscriber(session: Session, username: str) -> dict | None:
    """Find the current PPPoE session from the NAS, independent of accounting."""
    routers = session.exec(select(Router).where(Router.enabled == True)).all()
    for router in routers:
        try:
            for live in live_pppoe_traffic(router):
                if live.get("username") == username:
                    return {**live, "router_name": router.name, "nas_ip_address": router.host}
        except Exception as exc:  # noqa: BLE001 - another NAS can still hold the session
            logger.warning("Could not read client live session from %s: %s", router.host, exc)
    return None


def routeros_uptime_seconds(value: str | None) -> int:
    """Parse RouterOS PPP uptime such as 2h14m9s or 00:14:09."""
    if not value:
        return 0
    if ":" in value:
        try:
            hours, minutes, seconds = (int(part) for part in value.split(":"))
            return hours * 3600 + minutes * 60 + seconds
        except ValueError:
            return 0
    units = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(int(amount) * units[unit] for amount, unit in re.findall(r"(\d+)([wdhms])", value))


@app.get("/api/client/portal")
def client_portal(request: Request, session: SessionDep, identity: CurrentIdentity):
    if identity["role"] != Role.CLIENT.value:
        raise HTTPException(403, "Client login required")
    subscriber = session.exec(select(Subscriber).where(Subscriber.username == identity["sub"])).one()
    package = session.get(Package, subscriber.package_id)
    sessions = session.exec(
        select(AccountingSession)
        .where(AccountingSession.username == subscriber.username)
        .order_by(AccountingSession.updated_at.desc())
        .limit(30)
    ).all()
    live_session = live_session_for_subscriber(session, subscriber.username)
    source_ip = request.client.host if request.client else ""
    return {
        "subscriber": SubscriberRead.model_validate(subscriber),
        "package": package,
        "sessions": sessions,
        "live_session": live_session,
        "speed_test": {
            "eligible": bool(live_session),
            "source_ip": source_ip,
            "required_ip": subscriber.framed_ip_address,
            "reason": None if live_session else "Connect through your PPPoE service before running this test.",
        },
    }


def commit(session, item):
    try:
        session.add(item)
        session.commit()
        session.refresh(item)
        return item
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            409, "A record with that name, username, host, or IP already exists"
        ) from exc


def apply_pppoe_change(session, username: str) -> bool:
    """Drop one matching live session so RouterOS requests the latest RADIUS policy."""
    routers = session.exec(select(Router).where(Router.enabled == True)).all()
    for router in routers:
        try:
            if disconnect_subscriber(router, username):
                return True
        except Exception as exc:  # noqa: BLE001 - continue to the next configured NAS
            logger.warning("Could not disconnect %s on %s: %s", username, router.host, exc)
    return False


def refresh_radius_policy() -> None:
    """Regenerate and reload FreeRADIUS after an access-policy change."""
    sync_freeradius()
    try:
        for entry in Path("/proc").iterdir():
            if entry.name.isdigit() and (entry / "comm").read_text().strip() == "freeradius":
                os.kill(int(entry.name), signal.SIGHUP)
                return
        logger.warning("FreeRADIUS process was not found; generated policy will load on restart")
    except OSError as exc:
        logger.warning("FreeRADIUS policy generated but reload failed: %s", exc)


@app.get("/api/packages", response_model=list[PackageRead])
def list_packages(session: SessionDep, _: AdminIdentity):
    return session.exec(
        select(Package).order_by(Package.advertised_down_mbps, Package.advertised_up_mbps)
    ).all()


@app.post("/api/packages", response_model=PackageRead, status_code=201)
def create_package(data: PackageCreate, session: SessionDep, _: AdminIdentity):
    package = commit(session, Package(**data.model_dump(), provisioned_down_mbps=data.advertised_down_mbps + 1, provisioned_up_mbps=data.advertised_up_mbps + 1))
    refresh_radius_policy()
    return package


@app.patch("/api/packages/{package_id}", response_model=PackageRead)
def update_package(package_id: int, data: PackageUpdate, session: SessionDep, _: AdminIdentity):
    package = session.get(Package, package_id)
    if not package:
        raise HTTPException(404, "Package not found")
    values = data.model_dump(exclude_unset=True)
    if "advertised_down_mbps" in values:
        package.advertised_down_mbps = values["advertised_down_mbps"]
        package.provisioned_down_mbps = values["advertised_down_mbps"] + 1
    if "advertised_up_mbps" in values:
        package.advertised_up_mbps = values["advertised_up_mbps"]
        package.provisioned_up_mbps = values["advertised_up_mbps"] + 1
    for key in ("name", "enabled"):
        if key in values:
            setattr(package, key, values[key])
    package = commit(session, package)
    refresh_radius_policy()
    for subscriber in session.exec(select(Subscriber).where(Subscriber.package_id == package.id)).all():
        apply_pppoe_change(session, subscriber.username)
    return package


@app.delete("/api/packages/{package_id}", status_code=204)
def delete_package(package_id: int, session: SessionDep, _: AdminIdentity):
    package = session.get(Package, package_id)
    if not package:
        raise HTTPException(404, "Package not found")
    assigned = session.exec(select(Subscriber).where(Subscriber.package_id == package.id)).all()
    if assigned:
        raise HTTPException(409, f"Move or remove {len(assigned)} subscriber(s) before deleting this package")
    session.delete(package)
    session.commit()
    refresh_radius_policy()
    return Response(status_code=204)


@app.post("/api/imports/mikrotik-user-manager")
def import_mikrotik_user_manager(data: MikrotikUserManagerImport, session: SessionDep, _: SuperAdminIdentity):
    """Import static PPPoE accounts from a RouterOS User Manager export.

    Existing usernames are skipped, so repeating the import is safe. The old
    rate is preserved as the provisioned rate; the customer-visible rate is
    one Mbps lower where possible, matching the platform's speed policy.
    """
    try:
        records = parse_user_manager_export(data.export_text)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    imported = skipped = invalid = 0
    packages: dict[tuple[float, float], Package] = {
        (item.provisioned_down_mbps, item.provisioned_up_mbps): item
        for item in session.exec(select(Package)).all()
    }
    existing_users = set(session.exec(select(Subscriber.username)).all())
    existing_ips = set(session.exec(select(Subscriber.framed_ip_address)).all())
    for record in records:
        if record.username in existing_users or record.address in existing_ips:
            skipped += 1
            continue
        try:
            down, up = split_rate(record.rate)
        except ValueError:
            invalid += 1
            continue
        key = (down, up)
        package = packages.get(key)
        if package is None:
            package = Package(
                name=f"{max(0.001, down - 1):g}/{max(0.001, up - 1):g} Mbps",
                advertised_down_mbps=max(0.001, down - 1),
                advertised_up_mbps=max(0.001, up - 1),
                provisioned_down_mbps=down,
                provisioned_up_mbps=up,
            )
            session.add(package)
            session.flush()
            packages[key] = package
        session.add(Subscriber(
            username=record.username,
            display_name=record.username,
            password_ciphertext=encrypt_secret(record.password),
            package_id=package.id,
            framed_ip_address=record.address,
            ip_kind="public" if not record.address.startswith(("10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.", "192.168.")) else "private",
            site_name="Imported from MikroTik User Manager",
            status=Status.SUSPENDED if record.disabled else Status.ACTIVE,
            uisp_client_id=record.uisp_client_id,
            uisp_link_confirmed=bool(record.uisp_client_id),
        ))
        existing_users.add(record.username)
        existing_ips.add(record.address)
        imported += 1
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "An imported user conflicts with existing data") from exc
    refresh_radius_policy()
    return {"found": len(records), "imported": imported, "skipped": skipped, "invalid": invalid}


@app.get("/api/subscribers", response_model=list[SubscriberRead])
def list_subscribers(session: SessionDep, _: AdminIdentity):
    return visible(session.exec(select(Subscriber).order_by(Subscriber.username)).all())


@app.post("/api/subscribers", response_model=SubscriberRead, status_code=201)
def create_subscriber(data: SubscriberCreate, session: SessionDep, _: AdminIdentity):
    if not session.get(Package, data.package_id):
        raise HTTPException(400, "Package does not exist")
    pool = session.get(IpPool, data.pool_id)
    if not pool or not pool.enabled:
        raise HTTPException(400, "IP pool does not exist or is disabled")
    used = set(session.exec(select(Subscriber.framed_ip_address)).all())
    start, end = int(ip_address(pool.start_address)), int(ip_address(pool.end_address))
    assigned = next((str(ip_address(value)) for value in range(start, end + 1) if str(ip_address(value)) not in used), None)
    if not assigned:
        raise HTTPException(409, "The selected IP pool is full")
    values = {"username": data.username, "display_name": data.username, "package_id": data.package_id, "framed_ip_address": assigned, "ip_kind": pool.kind, "site_name": "Unassigned", "password_ciphertext": encrypt_secret(data.password)}
    subscriber = commit(session, Subscriber.model_validate(values))
    refresh_radius_policy()
    return subscriber


@app.patch("/api/subscribers/{subscriber_id}", response_model=SubscriberRead)
def update_subscriber(subscriber_id: int, data: SubscriberUpdate, session: SessionDep, _: AdminIdentity):
    subscriber = session.get(Subscriber, subscriber_id)
    if not subscriber:
        raise HTTPException(404, "Subscriber not found")
    old_username = subscriber.username
    values = data.model_dump(exclude_unset=True)
    password, pool_id = values.pop("password", None), values.pop("pool_id", None)
    if password:
        subscriber.password_ciphertext = encrypt_secret(password)
    if pool_id:
        pool = session.get(IpPool, pool_id)
        if not pool:
            raise HTTPException(400, "IP pool does not exist")
        used = set(session.exec(select(Subscriber.framed_ip_address).where(Subscriber.id != subscriber_id)).all())
        assigned = next((str(ip_address(v)) for v in range(int(ip_address(pool.start_address)), int(ip_address(pool.end_address)) + 1) if str(ip_address(v)) not in used), None)
        if not assigned:
            raise HTTPException(409, "The selected IP pool is full")
        subscriber.framed_ip_address = assigned
        subscriber.ip_kind = pool.kind
    for key, value in values.items():
        setattr(subscriber, key, value)
    subscriber = commit(session, subscriber)
    refresh_radius_policy()
    apply_pppoe_change(session, old_username)
    return subscriber


@app.patch("/api/subscribers/{subscriber_id}/status", response_model=SubscriberRead)
def update_subscriber_status(
    subscriber_id: int, data: SubscriberStatusUpdate, session: SessionDep, _: AdminIdentity
):
    subscriber = session.get(Subscriber, subscriber_id)
    if not subscriber:
        raise HTTPException(404, "Subscriber not found")
    subscriber.status = data.status
    subscriber = commit(session, subscriber)
    refresh_radius_policy()

    # Force any live PPP session to reconnect and immediately receive the new policy.
    # Unreachable routers do not prevent the status from being saved; their next
    # authentication will still receive the correct policy.
    apply_pppoe_change(session, subscriber.username)
    return subscriber


@app.get("/api/routers", response_model=list[RouterRead])
def list_routers(session: SessionDep, _: AdminIdentity):
    return visible(session.exec(select(Router).order_by(Router.name)).all())


@app.post("/api/routers", response_model=RouterRead, status_code=201)
def create_router(data: RouterCreate, session: SessionDep, _: AdminIdentity):
    values = data.model_dump(exclude={"api_password"})
    values.update(
        api_password_ciphertext=encrypt_secret(data.api_password), api_username=data.api_username
    )
    router = commit(session, Router.model_validate(values))
    try:
        for key, value in inspect_router(router).items():
            setattr(router, key, value)
        router = commit(session, router)
        refresh_radius_policy()
        return router
    except Exception as exc:
        raise HTTPException(502, f"Router saved but API test failed: {type(exc).__name__}") from exc


@app.post("/api/routers/{router_id}/test", response_model=RouterRead)
def test_router(router_id: int, session: SessionDep, _: AdminIdentity):
    router = session.get(Router, router_id)
    if not router:
        raise HTTPException(404, "Router not found")
    try:
        for key, value in inspect_router(router).items():
            setattr(router, key, value)
        return commit(session, router)
    except Exception as exc:
        router.reachable = False
        commit(session, router)
        raise HTTPException(502, f"Router API test failed: {type(exc).__name__}") from exc


@app.post("/api/routers/{router_id}/pppoe-single-session")
def enable_router_pppoe_guard(router_id: int, session: SessionDep, _: AdminIdentity):
    router = session.get(Router, router_id)
    if not router:
        raise HTTPException(404, "Router not found")
    try:
        changed = enforce_one_pppoe_session_per_host(router)
    except Exception as exc:
        raise HTTPException(502, f"Router PPPoE guard could not be enabled: {type(exc).__name__}") from exc
    return {"router": router.name, "servers_updated": changed, "enabled": True}


@app.patch("/api/routers/{router_id}", response_model=RouterRead)
def update_router(router_id: int, data: RouterUpdate, session: SessionDep, _: AdminIdentity):
    router = session.get(Router, router_id)
    if not router:
        raise HTTPException(404, "Router not found")
    values = data.model_dump(exclude_unset=True)
    password = values.pop("api_password", None)
    if password:
        router.api_password_ciphertext = encrypt_secret(password)
    for key, value in values.items():
        setattr(router, key, value)
    router = commit(session, router)
    refresh_radius_policy()
    return router


@app.get("/api/ip-pools")
def list_pools(session: SessionDep, _: AdminIdentity):
    pools = session.exec(select(IpPool).order_by(IpPool.name)).all()
    subscribers = visible(session.exec(select(Subscriber)).all())
    result = []
    for pool in pools:
        start, end = int(ip_address(pool.start_address)), int(ip_address(pool.end_address))
        used = sum(start <= int(ip_address(s.framed_ip_address)) <= end for s in subscribers)
        result.append({**pool.model_dump(), "used": used, "total": end - start + 1, "utilisation": round(used / (end - start + 1) * 100)})
    return result


@app.post("/api/ip-pools", response_model=IpPoolRead, status_code=201)
def create_pool(data: IpPoolCreate, session: SessionDep, _: AdminIdentity):
    try:
        start, end = ip_address(data.start_address), ip_address(data.end_address)
        if start.version != 4 or end.version != 4 or start > end:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(400, "Pool must be a valid ascending IPv4 range") from exc
    return commit(session, IpPool.model_validate(data))


@app.patch("/api/ip-pools/{pool_id}")
def update_pool(pool_id: int, data: IpPoolUpdate, session: SessionDep, _: AdminIdentity):
    pool = session.get(IpPool, pool_id)
    if not pool:
        raise HTTPException(404, "IP pool not found")
    values = data.model_dump(exclude_unset=True)
    start = ip_address(values.get("start_address", pool.start_address))
    end = ip_address(values.get("end_address", pool.end_address))
    if start.version != 4 or end.version != 4 or start > end:
        raise HTTPException(400, "Pool must be a valid ascending IPv4 range")
    assigned = session.exec(select(Subscriber.framed_ip_address)).all()
    original_start, original_end = ip_address(pool.start_address), ip_address(pool.end_address)
    excluded = [address for address in assigned if original_start <= ip_address(address) <= original_end and not (start <= ip_address(address) <= end)]
    if excluded:
        raise HTTPException(409, f"Pool change would exclude {len(excluded)} assigned address(es)")
    for key, value in values.items():
        setattr(pool, key, value)
    return commit(session, pool)


@app.get("/api/dashboard")
def dashboard(session: SessionDep, _: AdminIdentity):
    subscribers = visible(session.exec(select(Subscriber)).all())
    routers = visible(session.exec(select(Router)).all())
    sessions = visible(session.exec(select(AccountingSession)).all())
    active = [item for item in sessions if not item.stopped_at]
    # RouterOS is the immediate source of truth for the on-screen live count.
    # FreeRADIUS accounting supplies the historical graph once its records are
    # ingested, but it must never make a currently connected customer invisible.
    live_sessions = []
    live_errors = 0
    for router in routers:
        if not router.enabled:
            continue
        try:
            live_sessions.extend(live_pppoe_traffic(router))
        except Exception as exc:  # noqa: BLE001 - other reachable NAS devices still count
            live_errors += 1
            logger.warning("Could not read dashboard live sessions from %s: %s", router.host, exc)
    live_usernames = {item.get("username") for item in live_sessions if item.get("username")}
    # SQLite returns stored accounting timestamps without timezone information.
    now_time = datetime.now()  # noqa: DTZ005 - normalized to SQLite's naive timestamps
    # Build a meaningful timeline immediately from current RouterOS PPP
    # uptimes; RADIUS accounting supplements it with completed sessions.
    # This avoids a fabricated zero graph while accounting history fills in.
    series = []
    live_uptimes = {item["username"]: routeros_uptime_seconds(item.get("uptime")) for item in live_sessions if item.get("username")}
    for hours_ago in range(23, -1, -1):
        point = now_time - timedelta(hours=hours_ago)
        seconds_ago = hours_ago * 3600
        accounting_concurrent = sum(
            bool(item.started_at and item.started_at <= point and (not item.stopped_at or item.stopped_at >= point))
            for item in sessions
            if item.username not in live_uptimes
        )
        live_concurrent = sum(uptime >= seconds_ago for uptime in live_uptimes.values())
        series.append({"time": point.isoformat(), "sessions": accounting_concurrent + live_concurrent})
    pools = list_pools(session, _)
    return {
        "subscribers": len(subscribers),
        "online": len(live_usernames),
        "suspended": sum(s.status.value == "suspended" for s in subscribers),
        "unlinked": sum(not s.uisp_link_confirmed for s in subscribers),
        "routers_online": sum(r.reachable for r in routers),
        "routers_total": len(routers),
        "public_ips_used": sum(p["used"] for p in pools if p["kind"].lower() == "public"),
        "public_ips_total": sum(p["total"] for p in pools if p["kind"].lower() == "public"),
        "private_ips_used": sum(p["used"] for p in pools if p["kind"].lower() == "private"),
        "private_ips_total": sum(p["total"] for p in pools if p["kind"].lower() == "private"),
        "updated_at": now_time.isoformat(),
        "session_series": series,
        "session_history_ready": True,
        "services": {
            "api": "healthy",
            "database": "healthy",
            "radius": "healthy" if not live_errors else "attention",
            "uisp": "not_configured",
        },
        "attention": [
            *([{"type": "uisp", "message": f"{sum(not s.uisp_link_confirmed for s in subscribers)} subscribers need a UISP link"}] if any(not s.uisp_link_confirmed for s in subscribers) else []),
            *[{"type": "router", "message": f"{r.name} is unreachable", "last_checked_at": r.last_checked_at} for r in routers if not r.reachable],
        ],
    }


@app.get("/api/sessions")
def list_sessions(session: SessionDep, _: AdminIdentity):
    return visible(session.exec(
        select(AccountingSession).order_by(AccountingSession.updated_at.desc()).limit(500)
    ).all())


@app.post("/api/sessions/{session_id}/disconnect")
def disconnect_session(session_id: int, session: SessionDep, _: AdminIdentity):
    accounting = session.get(AccountingSession, session_id)
    if not accounting or accounting.stopped_at:
        raise HTTPException(404, "Live session not found")
    routers = session.exec(select(Router).where(Router.enabled == True)).all()
    router = next((r for r in routers if r.host == accounting.nas_ip_address), None)
    if not router or not disconnect_subscriber(router, accounting.username):
        raise HTTPException(502, "Session could not be found on the MikroTik")
    return {"disconnected": True, "username": accounting.username}


@app.get("/api/speed-tests")
def list_speed_tests(session: SessionDep, _: AdminIdentity):
    return session.exec(select(SpeedTest).order_by(SpeedTest.tested_at.desc()).limit(500)).all()


@app.post("/api/speed-tests", status_code=201)
def save_speed_test(data: dict, request: Request, session: SessionDep, identity: CurrentIdentity):
    if identity["role"] != Role.CLIENT.value:
        raise HTTPException(403, "Client login required")
    subscriber = session.exec(select(Subscriber).where(Subscriber.username == identity["sub"])).first()
    if not subscriber or not live_session_for_subscriber(session, subscriber.username):
        raise HTTPException(403, "Speed test must run through the subscriber PPPoE connection")
    required = ("download_mbps", "upload_mbps", "latency_ms")
    if any(key not in data for key in required):
        raise HTTPException(400, "Incomplete speed test")
    test = SpeedTest(
        username=identity["sub"],
        download_mbps=float(data["download_mbps"]), upload_mbps=float(data["upload_mbps"]),
        latency_ms=float(data["latency_ms"]), jitter_ms=float(data.get("jitter_ms", 0)),
        packet_loss_percent=float(data.get("packet_loss_percent", 0)), client_ip=data.get("client_ip"),
        user_agent=data.get("user_agent"), operating_system=data.get("operating_system"),
        device=data.get("device"), screen=data.get("screen"), raw_data=json.dumps(data, separators=(",", ":")),
    )
    return commit(session, test)


@app.get("/api/sessions/live-traffic")
def list_live_traffic(session: SessionDep, _: AdminIdentity):
    """Return live RouterOS interface rates, not cached accounting estimates."""
    rows = []
    for router in visible(session.exec(select(Router).where(Router.enabled == True)).all()):
        try:
            sessions = live_pppoe_traffic(router)
        except (OSError, ValueError, routeros_api.exceptions.RouterOsApiError) as exc:
            logger.warning("Could not read live traffic from %s: %s", router.host, exc)
            continue
        counts: dict[str, int] = {}
        for live in sessions:
            counts[live["username"]] = counts.get(live["username"], 0) + 1
        for live in sessions:
            live.update(
                {
                    "id": f'{router.id}:{live["session_id"]}',
                    "router_id": router.id,
                    "router_name": router.name,
                    "site_name": router.site_name,
                    "nas_ip_address": router.host,
                    "duplicate": counts[live["username"]] > 1,
                }
            )
            rows.append(live)
    return rows


@app.post("/api/sessions/live-traffic/{router_id}/{username}/disconnect")
def disconnect_live_traffic(router_id: int, username: str, session: SessionDep, _: AdminIdentity):
    router = session.get(Router, router_id)
    if not router or not disconnect_subscriber(router, username):
        raise HTTPException(404, "Live session could not be found on the MikroTik")
    return {"disconnected": True, "username": username}


@app.get("/api/speed-test/ping")
def speed_test_ping(identity: CurrentIdentity):
    return {"ok": True}


@app.get("/api/speed-test/download")
def speed_test_download(request: Request, session: SessionDep, identity: CurrentIdentity, bytes_count: int = 5_000_000):
    subscriber = session.exec(select(Subscriber).where(Subscriber.username == identity["sub"])).first()
    if not subscriber or not live_session_for_subscriber(session, subscriber.username):
        raise HTTPException(403, "Speed test must run through the subscriber PPPoE connection")
    size = min(max(bytes_count, 100_000), 25_000_000)
    return Response(
        content=b"0" * size,
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/speed-test/upload")
async def speed_test_upload(request: Request, session: SessionDep, identity: CurrentIdentity):
    subscriber = session.exec(select(Subscriber).where(Subscriber.username == identity["sub"])).first()
    if not subscriber or not live_session_for_subscriber(session, subscriber.username):
        raise HTTPException(403, "Speed test must run through the subscriber PPPoE connection")
    body = await request.body()
    return {"received": len(body)}


@app.get("/api/branding")
def get_branding():
    data = {"company_name": "WISP", "portal_hostname": "", "has_logo": LOGO_FILE.exists()}
    if BRANDING_FILE.exists():
        data.update(json.loads(BRANDING_FILE.read_text(encoding="utf-8")))
    return data


@app.put("/api/branding")
async def save_branding(request: Request, identity: CurrentIdentity):
    if identity["role"] not in (Role.SUPER_ADMIN.value, Role.WISP_ADMIN.value):
        raise HTTPException(403, "Administrator login required")
    data = await request.json()
    BRANDING_FILE.parent.mkdir(exist_ok=True)
    BRANDING_FILE.write_text(json.dumps({"company_name": str(data.get("company_name", "WISP"))[:100], "portal_hostname": str(data.get("portal_hostname", ""))[:200]}), encoding="utf-8")
    return get_branding()


@app.put("/api/branding/logo")
async def upload_logo(request: Request, identity: CurrentIdentity):
    if identity["role"] not in (Role.SUPER_ADMIN.value, Role.WISP_ADMIN.value):
        raise HTTPException(403, "Administrator login required")
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    allowed = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml"}
    if content_type not in allowed:
        raise HTTPException(400, "Logo must be PNG, JPG, WebP, SVG or GIF")
    body = await request.body()
    if not body or len(body) > 5_000_000:
        raise HTTPException(400, "Logo must be between 1 byte and 5 MB")
    LOGO_FILE.parent.mkdir(exist_ok=True)
    LOGO_FILE.write_bytes(body)
    (LOGO_FILE.with_suffix(".type")).write_text(content_type)
    return {"has_logo": True}


@app.get("/api/branding/logo")
def branding_logo():
    if not LOGO_FILE.exists():
        raise HTTPException(404, "No logo uploaded")
    type_file = LOGO_FILE.with_suffix(".type")
    return Response(content=LOGO_FILE.read_bytes(), media_type=type_file.read_text() if type_file.exists() else "image/png", headers={"Cache-Control": "no-cache"})


web_dist = Path("web_dist")
if web_dist.exists():
    app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
