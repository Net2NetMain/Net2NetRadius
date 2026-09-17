"""Register the authorized home-lab routers without storing plaintext credentials."""

from getpass import getpass
from json import dumps

from fastapi.testclient import TestClient

from app.main import app

if __name__ == "__main__":
    password = getpass("RouterOS API password: ")
    routers = [
        ("Home PPPoE hEX", "192.168.100.173", "Home Lab"),
        ("Home PoE Switch", "192.168.100.174", "Home Lab"),
    ]
    with TestClient(app) as client:
        results = []
        for name, host, site in routers:
            response = client.post(
                "/api/routers",
                json={
                    "name": name,
                    "host": host,
                    "site_name": site,
                    "api_port": 8728,
                    "api_username": "admin",
                    "api_password": password,
                    "enabled": True,
                },
            )
            results.append(
                {"host": host, "status": response.status_code, "result": response.json()}
            )
        print(dumps(results, indent=2, default=str))
