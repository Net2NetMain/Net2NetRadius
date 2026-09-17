"""Apply or roll back the isolated Net2Net home-lab PPPoE/RADIUS test."""

import argparse
import json
import time
from pathlib import Path

import routeros_api
from sqlmodel import Session, select

from app.database import engine
from app.models import Router
from app.security import decrypt_secret

TAG = "Net2Net-Lab-Test"
SERVER_NAME = "net2net-lab"
CLIENT_NAME = "net2net-radius-test"
BACKUP = Path("data/lab-router-backup.json")


def connect(router: Router):
    pool = routeros_api.RouterOsApiPool(
        router.host,
        username=router.api_username,
        password=decrypt_secret(router.api_password_ciphertext),
        port=router.api_port,
        plaintext_login=True,
        use_ssl=False,
    )
    return pool, pool.get_api()


def remove_matching(resource, **query):
    for item in resource.get(**query):
        resource.remove(id=item["id"])


def rollback(server_api, client_api, original_aaa: dict):
    remove_matching(client_api.get_resource("/interface/pppoe-client"), name=CLIENT_NAME)
    remove_matching(
        server_api.get_resource("/interface/pppoe-server/server"), service_name=SERVER_NAME
    )
    remove_matching(server_api.get_resource("/ppp/profile"), name=SERVER_NAME)
    remove_matching(server_api.get_resource("/radius"), comment=TAG)
    server_api.get_resource("/ppp/aaa").set(
        use_radius=original_aaa.get("use-radius", "false"),
        accounting=original_aaa.get("accounting", "true"),
        interim_update=original_aaa.get("interim-update", "0s"),
    )


def main(mode: str):
    with Session(engine) as session:
        radius_router = session.exec(select(Router).where(Router.host == "192.168.100.173")).one()
        client_router = session.exec(select(Router).where(Router.host == "192.168.100.174")).one()
    server_pool, server_api = connect(radius_router)
    client_pool, client_api = connect(client_router)
    original_aaa = server_api.get_resource("/ppp/aaa").get()[0]
    try:
        if mode == "rollback":
            if BACKUP.exists():
                original_aaa = json.loads(BACKUP.read_text())["ppp_aaa"]
            rollback(server_api, client_api, original_aaa)
            print("Lab RADIUS/PPPoE changes rolled back.")
            return
        BACKUP.write_text(json.dumps({"ppp_aaa": original_aaa}, indent=2))
        radius = server_api.get_resource("/radius")
        if not radius.get(comment=TAG):
            radius.add(address="192.168.100.201", secret="12345678", service="ppp", comment=TAG)
        server_api.get_resource("/ppp/aaa").set(
            use_radius="yes", accounting="yes", interim_update="5m"
        )
        pppoe_servers = server_api.get_resource("/interface/pppoe-server/server")
        profiles = server_api.get_resource("/ppp/profile")
        if not profiles.get(name=SERVER_NAME):
            profiles.add(name=SERVER_NAME, local_address="10.250.0.1")
        if not pppoe_servers.get(service_name=SERVER_NAME):
            pppoe_servers.add(
                interface="bridge1",
                service_name=SERVER_NAME,
                default_profile=SERVER_NAME,
                authentication="pap",
                disabled="no",
            )
        else:
            current_server = pppoe_servers.get(service_name=SERVER_NAME)[0]
            pppoe_servers.set(id=current_server["id"], default_profile=SERVER_NAME)
        clients = client_api.get_resource("/interface/pppoe-client")
        remove_matching(clients, name=CLIENT_NAME)
        clients.add(
            name=CLIENT_NAME,
            interface="bridge1",
            user="lab-test@example.local",
            password="lab-test-password",
            service_name=SERVER_NAME,
            add_default_route="no",
            use_peer_dns="no",
            disabled="no",
        )
        time.sleep(5)
        client_state = clients.get(name=CLIENT_NAME)[0]
        active = server_api.get_resource("/ppp/active").get(name="lab-test@example.local")
        safe_state = {
            key: client_state.get(key)
            for key in (
                "name",
                "running",
                "status",
                "local-address",
                "remote-address",
                "last-link-down-time",
                "last-disconnect-reason",
            )
        }
        active_safe = [
            {
                key: item.get(key)
                for key in ("name", "service", "caller-id", "address", "uptime", "encoding")
            }
            for item in active
        ]
        print(json.dumps({"client": safe_state, "server_active_sessions": active_safe}, indent=2))
        if client_state.get("running") != "true" or not active:
            logs = server_api.get_resource("/log").get()[-100:]
            messages = [
                item.get("message")
                for item in logs
                if any(
                    word in (item.get("topics", "") + item.get("message", "")).lower()
                    for word in ("ppp", "radius", "auth")
                )
            ]
            print(json.dumps({"recent_ppp_errors": messages[-10:]}, indent=2))
            raise RuntimeError(
                "PPPoE session did not become active; run with --rollback after diagnosis"
            )
    finally:
        server_pool.disconnect()
        client_pool.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("apply", "rollback"))
    main(parser.parse_args().mode)
