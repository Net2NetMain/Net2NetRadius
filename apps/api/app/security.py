import base64
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


def _fernet() -> Fernet:
    # Local appliances keep their encryption key in the mapped /data folder.
    # This lets an administrator manage all operational settings in the UI and
    # keeps backups/restores readable without editing Docker variables.
    key_path = Path(get_settings().data_dir) / "secret.key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if not key_path.exists():
        key_path.write_bytes(Fernet.generate_key())
    return Fernet(key_path.read_bytes())


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        # One-time compatibility for records created by pre-interface releases
        # that derived their key from the Docker APP_SECRET in production.
        digest = hashlib.sha256(get_settings().app_secret.encode()).digest()
        legacy = Fernet(base64.urlsafe_b64encode(digest))
        return legacy.decrypt(value.encode()).decode()
