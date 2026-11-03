from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from app import main
from app.accounting import UsageDelta, import_files, ingest
from app.auth import current_identity
from app.database import get_session
from app.models import AccountingSession, IpPool, Package, Subscriber


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'mobile.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "sync_freeradius", lambda: None)
    monkeypatch.setattr(main, "refresh_radius_policy", lambda: None)
    with Session(engine) as session:
        session.add(
            Package(
                id=1,
                name="Test",
                advertised_down_mbps=5,
                advertised_up_mbps=5,
                provisioned_down_mbps=6,
                provisioned_up_mbps=6,
            )
        )
        session.add(
            IpPool(
                id=1, name="Test", kind="private", start_address="10.0.0.1", end_address="10.0.0.9"
            )
        )
        session.add(
            Subscriber(
                id=1,
                username="customer",
                display_name="Customer",
                package_id=1,
                framed_ip_address="10.0.0.1",
                ip_kind="private",
                password_ciphertext="unused",
            )
        )
        session.commit()

    def database():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[get_session] = database
    client = TestClient(main.app)
    yield client, engine
    main.app.dependency_overrides.clear()
    engine.dispose()


def as_user(role, username="customer"):
    main.app.dependency_overrides[current_identity] = lambda: {
        "sub": username,
        "role": role,
        "name": username,
    }


def test_customer_cannot_mutate_or_access_admin_routes(isolated):
    client, _ = isolated
    as_user("client")
    assert (
        client.request("DELETE", "/api/subscribers/1", json={"confirmation": "Delete"}).status_code
        == 403
    )
    assert client.post("/api/mobile/subscribers/1/reconnect").status_code == 403
    assert client.get("/api/mobile/backups").status_code == 403
    assert client.get("/api/subscribers").status_code == 403


def test_delete_requires_exact_confirmation_and_preserves_history(isolated):
    client, engine = isolated
    as_user("wisp_admin")
    with Session(engine) as session:
        session.add(AccountingSession(acct_session_id="old", username="customer"))
        session.commit()
    for word in ("", "delete", "DELETE", "yes"):
        assert (
            client.request("DELETE", "/api/subscribers/1", json={"confirmation": word}).status_code
            == 400
        )
    assert (
        client.request("DELETE", "/api/subscribers/1", json={"confirmation": "Delete"}).status_code
        == 204
    )
    with Session(engine) as session:
        assert session.get(Subscriber, 1) is None
        assert len(session.exec(select(AccountingSession)).all()) == 1


def test_usage_is_scoped_to_logged_in_customer(isolated):
    client, engine = isolated
    with Session(engine) as session:
        session.add(
            AccountingSession(
                acct_session_id="mine", username="customer", output_bytes=400, input_bytes=50
            )
        )
        session.add(
            AccountingSession(
                acct_session_id="other", username="other", output_bytes=9000, input_bytes=5000
            )
        )
        session.add(
            UsageDelta(
                event="mine",
                username="customer",
                sampled_at=datetime(2026, 11, 3, tzinfo=UTC),
                download_bytes=400,
                upload_bytes=50,
            )
        )
        session.commit()
    as_user("client")
    data = client.get("/api/mobile/usage").json()
    assert data["download_bytes"] == 400
    assert data["daily"] == [{"period": "2026-11-03", "download_bytes": 400, "upload_bytes": 50}]
    as_user("wisp_admin")
    assert client.get("/api/mobile/usage").status_code == 403


def test_detail_import_is_resumable_idempotent_and_handles_partial_records(isolated, tmp_path):
    _, engine = isolated
    folder = tmp_path / "accounting" / "10.0.0.2"
    folder.mkdir(parents=True)
    file = folder / "detail-20261103"
    record = (
        b'\tUser-Name = "customer"\n\tAcct-Session-Id = "123"\n'
        b"\tNAS-IP-Address = 10.0.0.2\n\tAcct-Output-Octets = 400\n"
        b"\tAcct-Input-Octets = 50\n\tTimestamp = 1793664000\n\n"
    )
    file.write_bytes(record[:-1])
    import_files(folder.parent, engine)
    with Session(engine) as session:
        assert not session.exec(select(AccountingSession)).all()
    file.write_bytes(record)
    import_files(folder.parent, engine)
    import_files(folder.parent, engine)
    with Session(engine) as session:
        assert len(session.exec(select(AccountingSession)).all()) == 1
        assert len(session.exec(select(UsageDelta)).all()) == 1
    with file.open("ab") as stream:
        stream.write(record + record)
    import_files(folder.parent, engine)
    with Session(engine) as session:
        assert len(session.exec(select(UsageDelta)).all()) == 1
    # A second NAS may reuse the same session id; it must not overwrite the first.
    with Session(engine) as session:
        ingest(
            {
                "User-Name": "customer",
                "Acct-Session-Id": "123",
                "NAS-IP-Address": "10.0.0.3",
                "Timestamp": "1793664001",
                "Acct-Output-Octets": "100",
            },
            session,
        )
        session.commit()
        assert len(session.exec(select(AccountingSession)).all()) == 2


def test_counter_deltas_do_not_double_count_duplicate_or_late_packets(isolated):
    _, engine = isolated
    base = {"User-Name": "customer", "Acct-Session-Id": "deltas", "NAS-IP-Address": "10.0.0.2"}
    with Session(engine) as session:
        for stamp, total in ((100, 50), (200, 90), (200, 90), (150, 75)):
            ingest({**base, "Timestamp": str(stamp), "Acct-Output-Octets": str(total)}, session)
            session.commit()
        assert sum(row.download_bytes for row in session.exec(select(UsageDelta)).all()) == 90


def test_disabled_or_deleted_customer_loses_existing_session(isolated):
    from app.auth import create_token
    from app.models import Status
    from fastapi import HTTPException

    _, engine = isolated
    token = create_token("customer", "client", "Customer")
    with Session(engine) as session:
        assert current_identity(session, token)["sub"] == "customer"
        customer = session.get(Subscriber, 1)
        customer.status = Status.DISABLED
        session.add(customer)
        session.commit()
        with pytest.raises(HTTPException) as error:
            current_identity(session, token)
        assert error.value.status_code == 401
        session.delete(customer)
        session.commit()
        with pytest.raises(HTTPException):
            current_identity(session, token)
