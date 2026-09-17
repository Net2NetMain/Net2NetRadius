from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def login_admin() -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "superadmin", "password": "ChangeMe-Net2Net-2026!"},
    )
    assert response.status_code == 200


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_admin_routes_require_a_login() -> None:
    anonymous = TestClient(app)
    response = anonymous.get("/api/dashboard")
    assert response.status_code == 401


def test_dashboard_contract() -> None:
    login_admin()
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    assert response.json()["subscribers"] >= response.json()["online"]


def test_package_separates_advertised_and_provisioned_rates() -> None:
    login_admin()
    package = client.get("/api/packages").json()[0]
    assert package["advertised_down_mbps"] == 5
    assert package["provisioned_down_mbps"] == 6
