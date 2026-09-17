"""Read-only topology inventory for registered home-lab routers."""

from json import dumps

import routeros_api
from sqlmodel import Session, select

from app.database import engine
from app.models import Router
from app.security import decrypt_secret

KEEP = {
    "/ip/address": {"address", "interface", "disabled"},
    "/ip/neighbor": {"address", "identity", "interface", "mac-address", "platform", "version"},
    "/interface/bridge/port": {"interface", "bridge", "hw", "disabled"},
    "/interface/ethernet": {"name", "running", "disabled", "default-name"},
    "/ppp/aaa": {"use-radius", "accounting", "interim-update"},
}


def filtered(items: list[dict], keys: set[str]) -> list[dict]:
    return [{key: item[key] for key in keys if key in item} for item in items]


with Session(engine) as session:
    routers = session.exec(select(Router)).all()
    result = []
    for router in routers:
        pool = routeros_api.RouterOsApiPool(
            router.host,
            username=router.api_username,
            password=decrypt_secret(router.api_password_ciphertext),
            port=router.api_port,
            plaintext_login=True,
            use_ssl=False,
        )
        api = pool.get_api()
        try:
            inventory = {
                path: filtered(api.get_resource(path).get(), keys) for path, keys in KEEP.items()
            }
            result.append({"router": router.name, "host": router.host, **inventory})
        finally:
            pool.disconnect()
    print(dumps(result, indent=2))
