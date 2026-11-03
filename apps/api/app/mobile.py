"""Additional API routes used by the native Android client."""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from .accounting import UsageDelta
from .database import SessionDep
from .models import AccountingSession, Role, Subscriber


def routes(current_identity, admin_identity, super_identity, settings, refresh_policy, reconnect):
    from typing import Annotated
    from fastapi import Depends

    router = APIRouter()
    # No future-annotations here: FastAPI resolves these closure-local aliases directly.
    Current = Annotated[dict, Depends(current_identity)]
    Admin = Annotated[dict, Depends(admin_identity)]
    Super = Annotated[dict, Depends(super_identity)]

    @router.get("/api/mobile/usage")
    def usage(session: SessionDep, identity: Current):
        if identity["role"] != Role.CLIENT.value:
            raise HTTPException(403, "Customer login required")
        username = identity["sub"]
        records = session.exec(
            select(AccountingSession).where(AccountingSession.username == username)
        ).all()
        deltas = session.exec(
            select(UsageDelta)
            .where(UsageDelta.username == username)
            .order_by(UsageDelta.sampled_at)
        ).all()
        daily, monthly = {}, {}
        for delta in deltas:
            for bucket, period in (
                (daily, delta.sampled_at.strftime("%Y-%m-%d")),
                (monthly, delta.sampled_at.strftime("%Y-%m")),
            ):
                row = bucket.setdefault(
                    period, {"period": period, "download_bytes": 0, "upload_bytes": 0}
                )
                row["download_bytes"] += delta.download_bytes
                row["upload_bytes"] += delta.upload_bytes
        return {
            "download_bytes": sum(row.output_bytes for row in records),
            "upload_bytes": sum(row.input_bytes for row in records),
            "daily": list(daily.values())[-31:],
            "monthly": list(monthly.values())[-12:],
            "updated_at": datetime.now(UTC).isoformat(),
            "note": "Recorded usage in UTC. Updates around midnight may fall on the following day. Earlier usage may have totals only. Missing history does not mean zero usage.",
        }

    @router.get("/api/mobile/backups")
    def backups(_: Super):
        folder = Path(settings.data_dir) / "backups"
        return [
            {"filename": file.name, "size_bytes": file.stat().st_size}
            for file in sorted(folder.glob("*.db"), key=lambda f: f.stat().st_mtime, reverse=True)
        ]

    @router.post("/api/mobile/subscribers/{subscriber_id}/reconnect")
    def reconnect_subscriber(subscriber_id: int, session: SessionDep, _: Admin):
        subscriber = session.get(Subscriber, subscriber_id)
        if not subscriber:
            raise HTTPException(404, "Subscriber not found")
        if not reconnect(session, subscriber.username):
            raise HTTPException(409, "No reachable active session found; nothing was disconnected")
        return {"message": "Session disconnected; the subscriber router can reconnect"}

    @router.delete("/api/subscribers/{subscriber_id}", status_code=204)
    def delete_subscriber(
        subscriber_id: int, data: DeleteConfirmation, session: SessionDep, _: Admin
    ):
        if data.confirmation != "Delete":
            raise HTTPException(400, "Type Delete exactly to remove this account")
        subscriber = session.get(Subscriber, subscriber_id)
        if not subscriber:
            raise HTTPException(404, "Subscriber not found")
        username = subscriber.username
        session.delete(subscriber)
        session.commit()
        refresh_policy()
        reconnect(session, username)
        return None

    return router


class DeleteConfirmation(BaseModel):
    confirmation: str
