"""Read-only validation of the active lab PPPoE session and dynamic shaping."""

from json import dumps

import routeros_api
from sqlmodel import Session, select

from app.database import engine
from app.models import Router
from app.security import decrypt_secret

with Session(engine) as session:
    router = session.exec(select(Router).where(Router.host == "192.168.100.173")).one()
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
    active = api.get_resource("/ppp/active").get(name="lab-test@example.local")
    queues = api.get_resource("/queue/simple").get(dynamic="true")
    result = {
        "active": [
            {key: item.get(key) for key in ("name", "service", "caller-id", "address", "uptime")}
            for item in active
        ],
        "dynamic_queues": [
            {key: item.get(key) for key in ("name", "target", "max-limit", "rate")}
            for item in queues
            if "lab-test" in item.get("name", "")
        ],
    }
    print(dumps(result, indent=2))
finally:
    pool.disconnect()
