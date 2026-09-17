from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(UTC)


class Status(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class Role(StrEnum):
    SUPER_ADMIN = "super_admin"
    WISP_ADMIN = "wisp_admin"
    CLIENT = "client"


class AppUser(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, min_length=3, max_length=150)
    display_name: str = Field(min_length=2, max_length=150)
    role: Role
    password_hash: str
    enabled: bool = True
    created_at: datetime = Field(default_factory=now)


class AppUserCreate(SQLModel):
    username: str = Field(min_length=3, max_length=150)
    display_name: str = Field(min_length=2, max_length=150)
    password: str = Field(min_length=12, max_length=256)


class AppUserRead(SQLModel):
    id: int
    username: str
    display_name: str
    role: Role
    enabled: bool
    created_at: datetime


class PackageBase(SQLModel):
    name: str = Field(index=True, unique=True, min_length=2, max_length=80)
    advertised_down_mbps: float = Field(gt=0)
    advertised_up_mbps: float = Field(gt=0)
    provisioned_down_mbps: float = Field(gt=0)
    provisioned_up_mbps: float = Field(gt=0)
    enabled: bool = True


class Package(PackageBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=now)


class PackageCreate(SQLModel):
    name: str = Field(min_length=2, max_length=80)
    advertised_down_mbps: float = Field(gt=0)
    advertised_up_mbps: float = Field(gt=0)


class PackageUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    advertised_down_mbps: float | None = Field(default=None, gt=0)
    advertised_up_mbps: float | None = Field(default=None, gt=0)
    enabled: bool | None = None


class PackageRead(PackageBase):
    id: int


class SubscriberBase(SQLModel):
    username: str = Field(index=True, unique=True, min_length=3, max_length=150)
    display_name: str = Field(min_length=2, max_length=150)
    package_id: int = Field(foreign_key="package.id")
    framed_ip_address: str = Field(index=True, unique=True)
    ip_kind: str
    site_name: str = Field(default="Unassigned", max_length=100)
    status: Status = Status.ACTIVE
    uisp_client_id: str | None = Field(default=None, index=True)
    uisp_link_confirmed: bool = False


class Subscriber(SubscriberBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    password_ciphertext: str
    created_at: datetime = Field(default_factory=now)


class SubscriberCreate(SQLModel):
    username: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=4, max_length=128)
    package_id: int
    pool_id: int


class SubscriberUpdate(SQLModel):
    username: str | None = None
    password: str | None = None
    package_id: int | None = None
    pool_id: int | None = None
    status: Status | None = None
    uisp_client_id: str | None = None
    uisp_link_confirmed: bool | None = None


class SubscriberRead(SubscriberBase):
    id: int


class SubscriberStatusUpdate(SQLModel):
    status: Status


class MikrotikUserManagerImport(SQLModel):
    export_text: str = Field(min_length=100)


class RouterBase(SQLModel):
    name: str = Field(index=True, unique=True, min_length=2, max_length=100)
    host: str = Field(index=True, unique=True)
    site_name: str = Field(max_length=100)
    api_port: int = Field(default=8728, ge=1, le=65535)
    # RouterOS can source RADIUS from an OSPF/loopback address different from
    # its management API address. Register that NAS address explicitly.
    radius_source_address: str | None = Field(default=None, max_length=45)
    enabled: bool = True


class Router(RouterBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    api_username: str
    api_password_ciphertext: str
    identity: str | None = None
    board_name: str | None = None
    routeros_version: str | None = None
    reachable: bool = False
    last_checked_at: datetime | None = None


class RouterCreate(RouterBase):
    api_username: str = "admin"
    api_password: str = Field(min_length=1)


class RouterUpdate(SQLModel):
    name: str | None = None
    host: str | None = None
    site_name: str | None = None
    api_port: int | None = Field(default=None, ge=1, le=65535)
    radius_source_address: str | None = Field(default=None, max_length=45)
    api_username: str | None = None
    api_password: str | None = None
    enabled: bool | None = None


class RouterRead(RouterBase):
    id: int
    identity: str | None
    board_name: str | None
    routeros_version: str | None
    reachable: bool
    last_checked_at: datetime | None


class IpPoolBase(SQLModel):
    name: str = Field(unique=True, min_length=2, max_length=100)
    kind: str
    start_address: str
    end_address: str
    enabled: bool = True


class IpPool(IpPoolBase, table=True):
    id: int | None = Field(default=None, primary_key=True)


class IpPoolCreate(IpPoolBase):
    pass


class IpPoolUpdate(SQLModel):
    name: str | None = None
    kind: str | None = None
    start_address: str | None = None
    end_address: str | None = None
    enabled: bool | None = None


class IpPoolRead(IpPoolBase):
    id: int


class AccountingSession(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    acct_session_id: str = Field(index=True, unique=True)
    username: str = Field(index=True)
    nas_ip_address: str | None = Field(default=None, index=True)
    framed_ip_address: str | None = None
    calling_station_id: str | None = None
    started_at: datetime | None = None
    updated_at: datetime = Field(default_factory=now)
    stopped_at: datetime | None = None
    input_bytes: int = 0
    output_bytes: int = 0
    session_seconds: int = 0
    terminate_cause: str | None = None


class SpeedTest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True)
    tested_at: datetime = Field(default_factory=now, index=True)
    download_mbps: float
    upload_mbps: float
    latency_ms: float
    jitter_ms: float = 0
    packet_loss_percent: float = 0
    client_ip: str | None = None
    user_agent: str | None = None
    operating_system: str | None = None
    device: str | None = None
    screen: str | None = None
    raw_data: str
