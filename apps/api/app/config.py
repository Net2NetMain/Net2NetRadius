from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Net2Net Local RADIUS Manager"
    app_env: str = "development"
    app_secret: str = "development-only-secret"
    database_url: str = "sqlite:///./data/net2net.db"
    data_dir: str = "./data"
    web_origin: str = "http://localhost:5173"
    uisp_base_url: str = ""
    uisp_api_token: str = ""
    uisp_sync_minutes: int = 5
    suspension_rate: str = "8k/8k"
    data_retention_months: int = 24
    bootstrap_superadmin_username: str = "superadmin"
    bootstrap_superadmin_password: str = "ChangeMe-Net2Net-2026!"
    bootstrap_wispadmin_username: str = "wispadmin"
    bootstrap_wispadmin_password: str = "ChangeMe-WISP-2026!"
    radius_shared_secret: str = "12345678"
    # Optional private CIDR from which RouterOS may source RADIUS packets.
    # Configure per deployment; never bake a WISP's internal range into code.
    radius_client_network: str = ""
    duplicate_login_policy: str = "reject"
    backup_max_count: int = 14
    # Development/testing keeps lab records visible. A production deployment can
    # explicitly set SHOW_LAB_DATA=false in its environment after onboarding.
    show_lab_data: bool = True

    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    def validate_production(self) -> None:
        if self.app_env != "production":
            return
        unsafe = {"development-only-secret", "replace-with-a-long-random-value", "ChangeMe-Net2Net-2026!", "ChangeMe-WISP-2026!"}
        if len(self.app_secret) < 32 or self.app_secret in unsafe:
            raise RuntimeError("APP_SECRET must be a unique value of at least 32 characters in production")
        if self.bootstrap_superadmin_password in unsafe or len(self.bootstrap_superadmin_password) < 12:
            raise RuntimeError("Set a strong BOOTSTRAP_SUPERADMIN_PASSWORD before production startup")
        if self.bootstrap_wispadmin_password in unsafe or len(self.bootstrap_wispadmin_password) < 12:
            raise RuntimeError("Set a strong BOOTSTRAP_WISPADMIN_PASSWORD before production startup")
        if len(self.radius_shared_secret) < 12:
            raise RuntimeError("RADIUS_SHARED_SECRET must be at least 12 characters in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
