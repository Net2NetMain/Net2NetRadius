import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import routeros_api

from .models import Router
from .security import decrypt_secret


class _Connection:
    def __init__(self, router: Router):
        self.signature = (
            router.host,
            router.api_port,
            router.api_username,
            router.api_password_ciphertext,
        )
        self.lock = threading.RLock()
        self.pool = routeros_api.RouterOsApiPool(
            router.host,
            username=router.api_username,
            password=decrypt_secret(router.api_password_ciphertext),
            port=router.api_port,
            plaintext_login=True,
            use_ssl=False,
        )
        self.api = self.pool.get_api()

    def close(self) -> None:
        self.pool.disconnect()


_connections: dict[int, _Connection] = {}
_connections_lock = threading.Lock()


@contextmanager
def router_api(router: Router) -> Iterator[object]:
    """Reuse one RouterOS login per router and reconnect only after a real failure."""
    signature = (
        router.host,
        router.api_port,
        router.api_username,
        router.api_password_ciphertext,
    )
    with _connections_lock:
        connection = _connections.get(router.id)
        if connection and connection.signature != signature:
            connection.close()
            connection = None
        if connection is None:
            connection = _Connection(router)
            _connections[router.id] = connection
    try:
        with connection.lock:
            yield connection.api
    except BaseException:
        with _connections_lock:
            if _connections.get(router.id) is connection:
                _connections.pop(router.id, None)
                connection.close()
        raise


def inspect_router(router: Router) -> dict:
    with router_api(router) as api:
        identity = api.get_resource("/system/identity").get()[0]
        resource = api.get_resource("/system/resource").get()[0]
        return {
            "identity": identity.get("name"),
            "board_name": resource.get("board-name"),
            "routeros_version": resource.get("version"),
            "reachable": True,
            "last_checked_at": datetime.now(UTC),
        }


def disconnect_subscriber(router: Router, username: str) -> bool:
    """Remove an active PPP session so it reconnects with the latest RADIUS policy."""
    removed = False
    with router_api(router) as api:
        active = api.get_resource("/ppp/active")
        for item in active.get(name=username):
            active.remove(id=item["id"])
            removed = True
        return removed


def enforce_one_pppoe_session_per_host(router: Router) -> int:
    """Enable the RouterOS MAC-level guard on every PPPoE server at this site."""
    changed = 0
    with router_api(router) as api:
        servers = api.get_resource("/interface/pppoe-server/server")
        for item in servers.get():
            if item.get("one-session-per-host") != "true":
                servers.set(id=item["id"], **{"one-session-per-host": "yes"})
                changed += 1
    return changed


def live_pppoe_traffic(router: Router) -> list[dict]:
    """Read active PPPoE sessions and instantaneous interface counters from RouterOS."""
    with router_api(router) as api:
        active = api.get_resource("/ppp/active").get(service="pppoe")
        interface_resource = api.get_resource("/interface")
        interfaces = interface_resource.get(dynamic="true")
        by_username: dict[str, list[dict]] = {}
        for interface in interfaces:
            name = interface.get("name", "")
            match = re.fullmatch(r"<pppoe-(.+?)(?:-\d+)?>", name)
            if match:
                by_username.setdefault(match.group(1), []).append(interface)

        result = []
        occurrence: dict[str, int] = {}
        for item in active:
            username = item.get("name", "")
            index = occurrence.get(username, 0)
            occurrence[username] = index + 1
            matches = by_username.get(username, [])
            interface = matches[index] if index < len(matches) else {}
            rates = {}
            if interface.get("name"):
                samples = interface_resource.call(
                    "monitor-traffic", {"interface": interface["name"], "once": ""}
                )
                rates = samples[0] if samples else {}
            result.append(
                {
                    "session_id": item.get("session-id", item.get("id")),
                    "username": username,
                    "caller_id": item.get("caller-id"),
                    "ip_address": item.get("address"),
                    "uptime": item.get("uptime", "0s"),
                    "interface": interface.get("name"),
                    # From the NAS perspective RX is customer upload and TX is download.
                    "download_bps": int(rates.get("tx-bits-per-second", 0)),
                    "upload_bps": int(rates.get("rx-bits-per-second", 0)),
                    "download_bytes": int(interface.get("tx-byte", 0)),
                    "upload_bytes": int(interface.get("rx-byte", 0)),
                    "download_packets": int(interface.get("tx-packet", 0)),
                    "upload_packets": int(interface.get("rx-packet", 0)),
                }
            )
        return result
