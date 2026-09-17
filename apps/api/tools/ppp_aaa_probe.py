from getpass import getpass
from json import dumps

import routeros_api

password = getpass("RouterOS API password: ")
pool = routeros_api.RouterOsApiPool(
    "192.168.100.173",
    username="admin",
    password=password,
    port=8728,
    plaintext_login=True,
    use_ssl=False,
)
api = pool.get_api()
try:
    print(
        dumps(
            {
                "ppp_aaa": api.get_resource("/ppp/aaa").get(),
                "radius_count": len(api.get_resource("/radius").get()),
            },
            indent=2,
        )
    )
finally:
    pool.disconnect()
