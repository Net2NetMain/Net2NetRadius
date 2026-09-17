from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

settings = get_settings()
if settings.database_url.startswith("sqlite"):
    database_path = settings.database_url.removeprefix("sqlite:///")
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


def create_db() -> None:
    SQLModel.metadata.create_all(engine)
    # Lightweight forward migration for deployments created before the NAS
    # source-address field was introduced. SQLite does not add new columns via
    # create_all(), so make this idempotent migration explicit.
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as connection:
            columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(router)")}
            if "radius_source_address" not in columns:
                connection.exec_driver_sql("ALTER TABLE router ADD COLUMN radius_source_address VARCHAR(45)")


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
