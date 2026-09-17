"""Read-only RouterOS inventory probe. Never writes router configuration."""

from getpass import getpass
from json import dumps

import routeros_api


def compact(items: list[dict], allowed: set[str]) -> list[dict]:
    return [{key: item[key] for key in allowed if key in item} for item in items]


def probe(host: str, username: str, password: str) -> dict:
    pool = routeros_api.RouterOsApiPool(
        host,
        username=username,
        password=password,
        port=8728,
        plaintext_login=True,
        use_ssl=False,
    )
    api = pool.get_api()
    try:
        return {
            "host": host,
            "identity": api.get_resource("/system/identity").get(),
            "resource": compact(
                api.get_resource("/system/resource").get(),
                {"version", "board-name", "architecture-name", "uptime"},
            ),
            "radius": compact(
                api.get_resource("/radius").get(), {"address", "service", "src-address", "disabled"}
            ),
            "pppoe_servers": compact(
                api.get_resource("/interface/pppoe-server/server").get(),
                {"interface", "service-name", "authentication", "disabled"},
            ),
            "ppp_profiles": compact(
                api.get_resource("/ppp/profile").get(),
                {"name", "local-address", "remote-address", "use-radius"},
            ),
            "active_ppp": len(api.get_resource("/ppp/active").get()),
        }
    finally:
        pool.disconnect()


if __name__ == "__main__":
    secret = getpass("RouterOS API password: ")
    result = [probe(host, "admin", secret) for host in ("192.168.100.173", "192.168.100.174")]
    print(dumps(result, indent=2))
