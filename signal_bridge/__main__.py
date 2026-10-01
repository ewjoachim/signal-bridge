import logging
import mimetypes
import tempfile
import time
import traceback
from datetime import datetime
from email.message import EmailMessage
from importlib.metadata import version
from pathlib import Path

from signal_bridge import mail
from signal_bridge.config import Group, Settings
from signal_bridge.digest import digest_due, render_digest, render_welcome
from signal_bridge.events import Attachment
from signal_bridge.inbound import Inbound, match_group, parse_inbound
from signal_bridge.signal_cli import SignalCli
from signal_bridge.store import Store

logger = logging.getLogger("signal_bridge")

HEARTBEAT = Path("/tmp/signal-bridge.heartbeat")  # ruff: ignore[hardcoded-temp-file] -- read by the image HEALTHCHECK
ALERT_AFTER_FAILURES = 5


class Bridge:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.signal = SignalCli(settings.account, settings.signal_cli_dir)
        self.store = Store(settings.db_path)
        self.groups_by_id = {
            group.group_id: group for group in settings.groups.values()
        }

    def run_once(self) -> list[str]:
        failed = []
        for step in (
            self.welcome,
            self.receive,
            self.forward_emails,
            self.send_digests,
        ):
            try:
                step()
            except Exception:
                logger.exception("%s failed", step.__name__)
                failed.append(f"{step.__name__}:\n{traceback.format_exc()}")
        return failed

    def welcome(self) -> None:
        for group in self.settings.groups.values():
            if self.store.welcomed_email(group.group_id) == group.email:
                continue
            reply_to = self.settings.reply_address(group)
            mail.send(
                self.settings,
                render_welcome(
                    address=self.settings.address, reply_to=reply_to, group=group
                ),
            )
            self.store.set_welcomed_email(group.group_id, group.email)
            logger.info("Sent welcome email to %s", group.email)

    def receive(self) -> None:
        for raw in self.signal.receive():
            self.store.ingest(raw, self.settings.account, self.groups_by_id)
        HEARTBEAT.touch()

    def forward_emails(self) -> None:
        with mail.mailbox(self.settings) as box:
            for uid, email in box.messages():
                group = match_group(
                    email, self.settings.address, self.groups_by_id.values()
                )
                if group is None:
                    logger.warning("Rejecting email from %s", email.get("From"))
                    box.move(uid, mail.REJECTED)
                    continue
                inbound = parse_inbound(email)
                if inbound.text or inbound.files:
                    self.post(group, inbound)
                box.move(uid, mail.PROCESSED)

    def post(self, group: Group, inbound: Inbound) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for index, file in enumerate(inbound.files):
                path = Path(tmp) / str(index) / file.filename
                path.parent.mkdir()
                path.write_bytes(file.data)
                paths.append(path)
            self.signal.send_to_group(
                group.group_id, f"[{group.name}] {inbound.text}".rstrip(), paths
            )
        attachments = tuple(
            Attachment(
                filename=f.filename,
                content_type=mimetypes.guess_type(f.filename)[0] or "",
            )
            for f in inbound.files
        )
        self.store.add_own_message(
            group.group_id,
            group.name,
            time.time_ns() // 1_000_000,
            inbound.text,
            attachments,
        )
        logger.info("Posted email from %s to the group", group.email)

    def send_digests(self) -> None:
        now = datetime.now(self.settings.timezone)
        names = self.store.names()
        for slug, group in self.settings.groups.items():
            pending = self.store.pending(group.group_id)
            if not digest_due(pending, group.freq, now):
                continue
            email = render_digest(
                address=self.settings.address,
                reply_to=self.settings.reply_address(group),
                group=group,
                group_name=names.get(group.group_id, slug),
                messages=pending,
                tz=self.settings.timezone,
                read_attachment=self.read_attachment,
            )
            mail.send(self.settings, email)
            self.store.mark_digested(pending)
            for message in pending:
                for attachment in message.attachments:
                    if attachment.id:
                        self.signal.attachment_path(attachment.id).unlink(
                            missing_ok=True
                        )
            logger.info("Sent a digest of %d messages to %s", len(pending), group.email)

    def read_attachment(self, attachment_id: str) -> bytes | None:
        path = self.signal.attachment_path(attachment_id)
        return path.read_bytes() if path.exists() else None

    def alert(self, failures: list[str]) -> None:
        email = EmailMessage()
        email["From"] = self.settings.address
        email["To"] = self.settings.admin_email
        email["Subject"] = "signal-bridge is failing"
        email.set_content("\n\n".join(failures))
        try:
            mail.send(self.settings, email)
        except Exception:
            logger.exception("Could not send the alert email")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    settings = Settings()
    logger.info(
        "signal-bridge %s, bridging: %s",
        version("signal-bridge"),
        ", ".join(settings.groups),
    )
    bridge = Bridge(settings)
    streak = 0
    while True:
        failures = bridge.run_once()
        streak = streak + 1 if failures else 0
        if streak == ALERT_AFTER_FAILURES:
            bridge.alert(failures)
        time.sleep(settings.poll_interval.total_seconds())


if __name__ == "__main__":
    main()
