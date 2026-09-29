"""Persistent, encrypted local-appliance configuration.

Docker variables are only first-run fallbacks. Once saved in Settings, values
live in the WISP database and travel with the normal Net2Net backup.
"""
from sqlmodel import Session

from .config import get_settings
from .database import engine
from .models import PlatformConfiguration
from .security import decrypt_secret, encrypt_secret


def ensure_platform_configuration() -> None:
    settings = get_settings()
    with Session(engine) as session:
        record = session.get(PlatformConfiguration, 1)
        if record:
            return
        session.add(PlatformConfiguration(
            app_secret_ciphertext=encrypt_secret(settings.app_secret),
            radius_shared_secret_ciphertext=encrypt_secret(settings.radius_shared_secret),
            uisp_base_url=settings.uisp_base_url,
            uisp_api_token_ciphertext=encrypt_secret(settings.uisp_api_token) if settings.uisp_api_token else None,
        ))
        session.commit()


def _value(field: str, fallback: str) -> str:
    try:
        with Session(engine) as session:
            record = session.get(PlatformConfiguration, 1)
            encrypted = getattr(record, field, None) if record else None
            return decrypt_secret(encrypted) if encrypted else fallback
    except Exception:  # Database may not exist during first import/startup.
        return fallback


def application_secret() -> str:
    return _value("app_secret_ciphertext", get_settings().app_secret)


def radius_shared_secret() -> str:
    return _value("radius_shared_secret_ciphertext", get_settings().radius_shared_secret)


def uisp_api_token() -> str:
    return _value("uisp_api_token_ciphertext", get_settings().uisp_api_token)


def uisp_base_url() -> str:
    try:
        with Session(engine) as session:
            record = session.get(PlatformConfiguration, 1)
            return record.uisp_base_url if record and record.uisp_base_url else get_settings().uisp_base_url
    except Exception:
        return get_settings().uisp_base_url
