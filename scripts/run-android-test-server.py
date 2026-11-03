"""Disposable, loopback-only API for connected-phone tests. Never reads WISP appdata."""

import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))


def run():
    with tempfile.TemporaryDirectory(prefix="wisp-android-test-") as folder:
        os.environ.update(
            APP_ENV="development",
            DATA_DIR=folder,
            DATABASE_URL=f"sqlite:///{Path(folder).as_posix()}/test.db",
            BOOTSTRAP_SUPERADMIN_USERNAME="device-admin",
            BOOTSTRAP_SUPERADMIN_PASSWORD="Phone-test-2026!",
            BOOTSTRAP_WISPADMIN_PASSWORD="Phone-test-2026!",
        )
        from app.main import app
        from app.database import engine
        from app.models import Subscriber, Router, AccountingSession, SpeedTest
        from app.accounting import UsageDelta
        from app import main
        from app.security import encrypt_secret
        from sqlmodel import Session
        import uvicorn

        main.sync_freeradius = lambda: None
        main.disconnect_subscriber = lambda *args: False
        main.live_pppoe_traffic = lambda router: [
            {
                "session_id": "phone-live",
                "username": "phone-customer",
                "ip_address": "10.250.0.10",
                "uptime": "30m",
                "download_bps": 4200000,
                "upload_bps": 800000,
                "download_bytes": 209715200,
                "upload_bytes": 52428800,
            }
        ]

        with Session(engine) as session:
            session.add(
                Subscriber(
                    username="phone-customer",
                    display_name="Phone test customer",
                    package_id=1,
                    framed_ip_address="10.250.0.10",
                    ip_kind="private",
                    password_ciphertext=encrypt_secret("Phone-test-2026!"),
                )
            )
            stamp = datetime.now(UTC)
            session.add(
                Router(
                    name="Phone test router",
                    host="192.0.2.1",
                    site_name="Device test",
                    api_username="test",
                    api_password_ciphertext=encrypt_secret("Phone-test-2026!"),
                    reachable=True,
                )
            )
            session.add(
                AccountingSession(
                    acct_session_id="phone-history",
                    username="phone-customer",
                    started_at=stamp - timedelta(hours=1),
                    stopped_at=stamp - timedelta(minutes=30),
                    session_seconds=1800,
                    output_bytes=209715200,
                    input_bytes=52428800,
                )
            )
            session.add(
                UsageDelta(
                    event="phone-usage",
                    username="phone-customer",
                    sampled_at=stamp,
                    download_bytes=209715200,
                    upload_bytes=52428800,
                )
            )
            session.add(
                SpeedTest(
                    username="phone-customer",
                    download_mbps=4.8,
                    upload_mbps=4.5,
                    latency_ms=12,
                    raw_data="{}",
                )
            )
            session.commit()
        print("Disposable phone-test API: http://127.0.0.1:18080", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=18080)


if __name__ == "__main__":
    run()
