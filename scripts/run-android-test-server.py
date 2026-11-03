"""Disposable, loopback-only API for connected-phone tests. Never reads WISP appdata."""

import os
import sys
import tempfile
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
        from app.models import Subscriber
        from app.security import encrypt_secret
        from sqlmodel import Session
        import uvicorn

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
            session.commit()
        print("Disposable phone-test API: http://127.0.0.1:18080", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=18080)


if __name__ == "__main__":
    run()
