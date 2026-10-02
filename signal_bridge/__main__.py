import datetime
import email.message
import json
import logging
import mimetypes
import pathlib
import tempfile
import time
import traceback
from importlib import metadata

from signal_bridge import config, digest, events, inbound, mail, signal_cli, store

logger = logging.getLogger("signal_bridge")

HEARTBEAT = pathlib.Path("/tmp/signal-bridge.heartbeat")  # ruff: ignore[hardcoded-temp-file] -- read by the image HEALTHCHECK
ALERT_AFTER_FAILURES = 5


class Bridge:
    def __init__(self, settings: config.Settings) -> None:
        self.settings = settings
        self.signal = signal_cli.SignalCli(settings.account, settings.signal_cli_dir)
        self.store = store.Store(settings.db_path)
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
                digest.render_welcome(
                    address=self.settings.address, reply_to=reply_to, group=group
                ),
            )
            self.store.set_welcomed_email(group.group_id, group.email)
            logger.info("Sent welcome email to %s", group.email)

    def receive(self) -> None:
        # signal-cli acknowledges what it prints: a line we fail on is never redelivered.
        for line in self.signal.receive():
            try:
                self.store.ingest(
                    json.loads(line), self.settings.account, self.groups_by_id
                )
            except Exception:
                logger.exception(
                    "Could not process an envelope, saved to %s",
                    self.settings.unparsed_path,
                )
                with self.settings.unparsed_path.open("a") as unparsed:
                    unparsed.write(line.rstrip("\n") + "\n")
        HEARTBEAT.touch()

    def forward_emails(self) -> None:
        with mail.mailbox(self.settings) as box:
            for uid, msg in box.messages():
                group = inbound.match_group(
                    msg, self.settings.address, self.groups_by_id.values()
                )
                if group is None:
                    logger.warning("Rejecting email from %s", msg.get("From"))
                    box.move(uid, mail.REJECTED)
                    continue
                reply = inbound.parse_inbound(msg)
                if reply.text or reply.files:
                    self.post(group, reply)
                box.move(uid, mail.PROCESSED)

    def post(self, group: config.Group, reply: inbound.Inbound) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for index, file in enumerate(reply.files):
                path = pathlib.Path(tmp) / str(index) / file.filename
                path.parent.mkdir()
                path.write_bytes(file.data)
                paths.append(path)
            self.signal.send_to_group(
                group.group_id, f"[{group.name}] {reply.text}".rstrip(), paths
            )
        attachments = tuple(
            events.Attachment(
                filename=f.filename,
                content_type=mimetypes.guess_type(f.filename)[0] or "",
            )
            for f in reply.files
        )
        self.store.add_own_message(
            group.group_id,
            group.name,
            time.time_ns() // 1_000_000,
            reply.text,
            attachments,
        )
        logger.info("Posted email from %s to the group", group.email)

    def send_digests(self) -> None:
        now = datetime.datetime.now(self.settings.timezone)
        names = self.store.names()
        for slug, group in self.settings.groups.items():
            pending = self.store.pending(group.group_id)
            if not digest.digest_due(pending, group.freq, now):
                continue
            year, week_number, _ = now.isocalendar()
            week = f"{year}-W{week_number:02}"
            msg = digest.render_digest(
                address=self.settings.address,
                reply_to=self.settings.reply_address(group),
                group=group,
                group_name=names.get(group.group_id, slug),
                messages=pending,
                tz=self.settings.timezone,
                read_attachment=self.read_attachment,
                thread=self.store.thread(group.group_id, week),
            )
            mail.send(self.settings, msg)
            self.store.add_to_thread(group.group_id, week, str(msg["Message-ID"]))
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
        msg = email.message.EmailMessage()
        msg["From"] = self.settings.address
        msg["To"] = self.settings.admin_email
        msg["Subject"] = "signal-bridge is failing"
        msg.set_content("\n\n".join(failures))
        try:
            mail.send(self.settings, msg)
        except Exception:
            logger.exception("Could not send the alert email")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    settings = config.Settings()
    logger.info(
        "signal-bridge %s, bridging: %s",
        metadata.version("signal-bridge"),
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
