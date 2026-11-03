"""Import FreeRADIUS detail records without replaying counters after a restart.

The journal and offsets are additive tables; existing subscribers and backups are untouched.
Daily deltas belong to the UTC day on which the interim counter was sampled. A packet
straddling midnight is not fine-grained billing evidence and is labelled accordingly.
"""

import hashlib
import logging
import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import Field, Session, SQLModel, select

logger = logging.getLogger(__name__)


class AccountingFileOffset(SQLModel, table=True):
    path: str = Field(primary_key=True)
    offset: int = 0


class UsageDelta(SQLModel, table=True):
    event: str = Field(primary_key=True)
    username: str = Field(index=True)
    sampled_at: datetime = Field(index=True)
    download_bytes: int = 0
    upload_bytes: int = 0


def parse_detail(block: bytes) -> dict[str, str]:
    values = {}
    for line in block.decode("utf-8", errors="replace").splitlines():
        match = re.match(r"\s*([\w-]+)\s*=\s*(.*?)\s*$", line)
        if match:
            key, value = match.groups()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace(r"\"", '"').replace(r"\\", "\\")
            values[key] = value
    return values


def ingest(values: dict, session: Session) -> None:
    from .models import AccountingSession

    username, identifier = values.get("User-Name"), values.get("Acct-Session-Id")
    if not username or not identifier:
        return
    nas = values.get("NAS-IP-Address", values.get("Packet-Src-IP-Address", "unknown"))
    # NAS devices may reuse a session id. Include NAS and username in our internal key.
    key = hashlib.sha256(f"{nas}:{username}:{identifier}".encode()).hexdigest()
    stamp = int(values.get("Event-Timestamp", values.get("Timestamp", "0")))
    if stamp <= 0:
        logger.warning("Accounting record has no numeric timestamp; skipped")
        return
    sampled = datetime.fromtimestamp(stamp, UTC)
    seconds = int(values.get("Acct-Session-Time", "0"))
    download = int(values.get("Acct-Output-Octets", "0")) + (
        int(values.get("Acct-Output-Gigawords", "0")) << 32
    )
    upload = int(values.get("Acct-Input-Octets", "0")) + (
        int(values.get("Acct-Input-Gigawords", "0")) << 32
    )
    event = hashlib.sha256(
        f"{key}:{stamp}:{download}:{upload}:{values.get('Acct-Status-Type')}".encode()
    ).hexdigest()
    if session.get(UsageDelta, event):
        return
    record = session.exec(
        select(AccountingSession).where(AccountingSession.acct_session_id == key)
    ).first()
    previous_time = (
        record.updated_at.replace(tzinfo=UTC)
        if record and record.updated_at and record.updated_at.tzinfo is None
        else (record.updated_at if record else None)
    )
    if previous_time and sampled < previous_time:
        return  # Late/reordered packets must never move counters backwards.
    previous_down = record.output_bytes if record else 0
    previous_up = record.input_bytes if record else 0
    if record is None:
        record = AccountingSession(acct_session_id=key, username=username)
    record.nas_ip_address = nas
    record.framed_ip_address = values.get("Framed-IP-Address")
    record.calling_station_id = values.get("Calling-Station-Id")
    record.started_at = record.started_at or sampled - timedelta(seconds=seconds)
    record.updated_at = sampled
    record.session_seconds = max(record.session_seconds, seconds)
    record.output_bytes = max(previous_down, download)
    record.input_bytes = max(previous_up, upload)
    if values.get("Acct-Status-Type") in ("Stop", "2"):
        record.stopped_at = sampled
        record.terminate_cause = values.get("Acct-Terminate-Cause")
    session.add(record)
    session.add(
        UsageDelta(
            event=event,
            username=username,
            sampled_at=sampled,
            download_bytes=max(0, download - previous_down),
            upload_bytes=max(0, upload - previous_up),
        )
    )


def import_files(root: Path, engine) -> None:
    if not root.exists():
        return
    for file in sorted(root.glob("*/detail-*")):
        if not file.is_file():
            continue
        with Session(engine) as session:
            checkpoint = session.get(AccountingFileOffset, str(file)) or AccountingFileOffset(
                path=str(file)
            )
            if file.stat().st_size < checkpoint.offset:
                checkpoint.offset = 0
            with file.open("rb") as stream:
                stream.seek(checkpoint.offset)
                # Bound each pass; leave incomplete records to be read next time.
                data = stream.read(4 * 1024 * 1024)
            end = data.rfind(b"\n\n")
            if end < 0:
                continue
            complete = data[: end + 2]
            for block in complete.split(b"\n\n"):
                if not block.strip():
                    continue
                try:
                    ingest(parse_detail(block), session)
                except (ValueError, OverflowError) as exc:
                    logger.warning("Malformed accounting record skipped: %s", type(exc).__name__)
            checkpoint.offset += len(complete)
            session.add(checkpoint)
            session.commit()


def collect(stop: threading.Event, root: Path, engine) -> None:
    while not stop.is_set():
        try:
            import_files(root, engine)
        except Exception:
            logger.exception("Accounting import failed; will retry")
        stop.wait(5)
