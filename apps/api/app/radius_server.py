import hashlib
import logging
import select as socket_select
import threading
import time
from pathlib import Path
from typing import ClassVar

from pyrad import dictionary, packet, server
from sqlmodel import Session, select

from .config import get_settings
from .database import engine
from .models import AccountingSession, Package, Router, Status, Subscriber, now
from .routeros import disconnect_subscriber
from .security import decrypt_secret

log = logging.getLogger("net2net.radius")


class Net2NetRadius(server.Server):
    authorization_reservations: ClassVar[dict[str, tuple[str, float]]] = {}
    reservation_lock: ClassVar[threading.Lock] = threading.Lock()

    def _AddSecret(self, pkt):
        """Attach the NAS secret while retaining the source IP in diagnostics."""
        if pkt.source[0] in self.hosts:
            pkt.secret = self.hosts[pkt.source[0]].secret
        else:
            log.warning("dropping RADIUS packet from unregistered NAS %s", pkt.source[0])
            raise server.ServerPacketError("Received packet from unknown host")

    def Run(self):
        """Portable main loop; pyrad's default loop requires Unix select.poll."""
        sockets = self.authfds + self.acctfds + self.coafds
        self._realauthfds = [item.fileno() for item in self.authfds]
        self._realacctfds = [item.fileno() for item in self.acctfds]
        self._realcoafds = [item.fileno() for item in self.coafds]
        while True:
            readable, _, _ = socket_select.select(sockets, [], [], 1.0)
            for socket in readable:
                try:
                    self._ProcessInput(socket)
                except (server.ServerPacketError, packet.PacketError) as exc:
                    log.warning("dropping invalid RADIUS packet: %s", exc)

    def HandleAuthPacket(self, request):
        username_value = request.get("User-Name", [""])[0]
        username = (
            username_value.decode(errors="replace")
            if isinstance(username_value, bytes)
            else str(username_value)
        )
        reply = self.CreateReplyPacket(request)
        caller_value = request.get("Calling-Station-Id", [""])[0]
        caller = caller_value.decode(errors="replace") if isinstance(caller_value, bytes) else str(caller_value)
        with Session(engine) as session:
            subscriber = session.exec(
                select(Subscriber).where(Subscriber.username == username)
            ).first()
            if not subscriber or subscriber.status == Status.DISABLED:
                reply.code = packet.AccessReject
            else:
                expected_password = decrypt_secret(subscriber.password_ciphertext)
                pap_password = request.get("User-Password", [None])[0]
                chap_password = request.get("CHAP-Password", [None])[0]
                if pap_password is not None:
                    try:
                        supplied = request.PwDecrypt(pap_password)
                    except (TypeError, UnicodeError, ValueError):
                        supplied = ""
                    credentials_match = hmac.compare_digest(supplied, expected_password)
                elif chap_password is not None and len(chap_password) == 17:
                    challenge = request.get("CHAP-Challenge", [request.authenticator])[0]
                    digest = hashlib.md5(
                        chap_password[:1] + expected_password.encode() + challenge
                    ).digest()
                    credentials_match = hmac.compare_digest(chap_password[1:], digest)
                    supplied = "<CHAP>" if credentials_match else ""
                else:
                    credentials_match = False
                    supplied = ""
                if not credentials_match:
                    log.warning(
                        "password mismatch for %s (received length %d; expected length %d; attributes %s)",
                        username, len(supplied), len(expected_password), list(request.keys()),
                    )
                    reply.code = packet.AccessReject
                else:
                    # Accounting Start arrives after Access-Accept. This short reservation
                    # closes that race so two NAS devices cannot both be accepted.
                    with self.reservation_lock:
                        pending = self.authorization_reservations.get(username)
                        if pending and pending[1] <= time.monotonic():
                            self.authorization_reservations.pop(username, None)
                            pending = None
                        if pending and pending[0] != caller:
                            reply.code = packet.AccessReject
                        else:
                            self.authorization_reservations[username] = (caller, time.monotonic() + 15)
                    if reply.code == packet.AccessReject:
                        log.warning("duplicate PPPoE request rejected for %s from %s", username, caller)
                        reply.add_message_authenticator()
                        self.SendReplyPacket(request.fd, reply)
                        return
                    active = session.exec(
                        select(AccountingSession).where(
                            AccountingSession.username == username,
                            AccountingSession.stopped_at == None,
                        )
                    ).all()
                    if active:
                        settings = get_settings()
                        if settings.duplicate_login_policy == "replace":
                            for duplicate in active:
                                router = session.exec(
                                    select(Router).where(Router.host == duplicate.nas_ip_address)
                                ).first()
                                if router:
                                    try:
                                        disconnect_subscriber(router, username)
                                    except Exception as exc:  # noqa: BLE001 - do not accept if disconnect fails
                                        log.warning("duplicate disconnect failed for %s: %s", username, exc)
                                        reply.code = packet.AccessReject
                                        break
                        else:
                            reply.code = packet.AccessReject
                            log.warning("duplicate PPPoE login rejected for %s", username)
                    if reply.code == packet.AccessReject:
                        reply.add_message_authenticator()
                        self.SendReplyPacket(request.fd, reply)
                        return
                    package = session.get(Package, subscriber.package_id)
                    reply.code = packet.AccessAccept
                    reply["Service-Type"] = "Framed-User"
                    reply["Framed-Protocol"] = "PPP"
                    reply["Framed-IP-Address"] = subscriber.framed_ip_address
                    if subscriber.status == Status.SUSPENDED:
                        reply["Mikrotik-Rate-Limit"] = "8k/8k"
                    elif package:
                        reply["Mikrotik-Rate-Limit"] = (
                            f"{package.provisioned_up_mbps:g}M/{package.provisioned_down_mbps:g}M"
                        )
        reply.add_message_authenticator()
        self.SendReplyPacket(request.fd, reply)
        log.info(
            "authentication %s for %s",
            "accepted" if reply.code == packet.AccessAccept else "rejected",
            username,
        )

    def HandleAcctPacket(self, request):
        def value(name, default=None):
            item = request.get(name, [default])[0]
            return item.decode(errors="replace") if isinstance(item, bytes) else item

        session_id = str(value("Acct-Session-Id", ""))
        if session_id:
            with Session(engine) as session:
                record = session.exec(
                    select(AccountingSession).where(AccountingSession.acct_session_id == session_id)
                ).first() or AccountingSession(
                    acct_session_id=session_id, username=str(value("User-Name", ""))
                )
                status = value("Acct-Status-Type", "")
                record.nas_ip_address = str(value("NAS-IP-Address", request.source[0]))
                record.framed_ip_address = str(value("Framed-IP-Address", "")) or None
                record.calling_station_id = str(value("Calling-Station-Id", "")) or None
                record.session_seconds = int(value("Acct-Session-Time", 0) or 0)
                record.input_bytes = int(value("Acct-Input-Octets", 0) or 0) + (
                    int(value("Acct-Input-Gigawords", 0) or 0) << 32
                )
                record.output_bytes = int(value("Acct-Output-Octets", 0) or 0) + (
                    int(value("Acct-Output-Gigawords", 0) or 0) << 32
                )
                record.updated_at = now()
                if status in ("Start", 1):
                    previous = session.exec(
                        select(AccountingSession).where(
                            AccountingSession.username == record.username,
                            AccountingSession.nas_ip_address == record.nas_ip_address,
                            AccountingSession.stopped_at == None,
                            AccountingSession.acct_session_id != session_id,
                        )
                    ).all()
                    for old in previous:
                        old.stopped_at = now()
                        old.updated_at = old.stopped_at
                        old.terminate_cause = "Session-Replaced"
                        session.add(old)
                    record.started_at = record.started_at or now()
                elif status in ("Stop", 2):
                    record.stopped_at = now()
                    record.terminate_cause = str(value("Acct-Terminate-Cause", "")) or None
                session.add(record)
                session.commit()
        self.SendReplyPacket(request.fd, self.CreateReplyPacket(request))


def run(host: str = "0.0.0.0", secret: str | None = None):
    settings = get_settings()
    secret = secret or settings.radius_shared_secret
    radius = Net2NetRadius(
        dict=dictionary.Dictionary(str(Path(__file__).parents[1] / "radius" / "dictionary")),
        authport=1812,
        acctport=1813,
        addresses=[host],
    )
    with Session(engine) as session:
        routers = session.exec(select(Router).where(Router.enabled == True)).all()
    for router in routers:
        radius.hosts[router.host] = server.RemoteHost(router.host, secret.encode(), router.name)
        if router.radius_source_address and router.radius_source_address != router.host:
            radius.hosts[router.radius_source_address] = server.RemoteHost(
                router.radius_source_address, secret.encode(), f"{router.name} RADIUS source"
            )
    if settings.app_env == "development":
        radius.hosts["127.0.0.1"] = server.RemoteHost("127.0.0.1", secret.encode(), "localhost")
    log.info("RADIUS listening on UDP 1812/1813")
    radius.Run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
