from enum import StrEnum
from ipaddress import IPv4Address

from pydantic import BaseModel, Field


class Role(StrEnum):
    SUPER_ADMIN = "super_admin"
    WISP_ADMIN = "wisp_admin"
    CLIENT = "client"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    UNLINKED = "unlinked"


class Package(BaseModel):
    id: int
    name: str
    advertised_down_mbps: int = Field(gt=0)
    advertised_up_mbps: int = Field(gt=0)
    provisioned_down_mbps: int = Field(gt=0)
    provisioned_up_mbps: int = Field(gt=0)
    subscribers: int = 0


class Subscriber(BaseModel):
    id: int
    username: str
    display_name: str
    status: AccountStatus
    package: str
    ip_address: IPv4Address
    ip_kind: str
    site: str
    uisp_client_id: str | None = None
    online: bool = False


class Router(BaseModel):
    id: int
    name: str
    loopback_ip: IPv4Address
    site: str
    online: bool
    active_sessions: int = 0


class DashboardSummary(BaseModel):
    subscribers: int
    online: int
    suspended: int
    unlinked: int
    routers_online: int
    routers_total: int
    public_ips_used: int
    public_ips_total: int
    private_ips_used: int
    private_ips_total: int
