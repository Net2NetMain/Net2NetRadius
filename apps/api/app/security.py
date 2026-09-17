import base64
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet

from .config import get_settings


def _fernet() -> Fernet:
    if get_settings().app_env == "development":
        # Keep the development key beside the SQLite database.  A container
        # replacement must not make existing subscriber credentials unreadable.
        key_path = Path(get_settings().data_dir) / "secret.key"
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if not key_path.exists():
            key_path.write_bytes(Fernet.generate_key())
        return Fernet(key_path.read_bytes())
    digest = hashlib.sha256(get_settings().app_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()
