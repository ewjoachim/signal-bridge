import email
import imaplib
import smtplib
import ssl
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from email import policy
from email.message import EmailMessage

from signal_bridge.config import Settings

PROCESSED = "Processed"
REJECTED = "Rejected"


IMPLICIT_TLS_PORT = 465


def send(settings: Settings, message: EmailMessage) -> None:
    context = ssl.create_default_context()
    if settings.smtp_port == IMPLICIT_TLS_PORT:
        smtp = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context)
    else:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
        smtp.starttls(context=context)
    with smtp:
        smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


class Mailbox:
    def __init__(self, conn: imaplib.IMAP4_SSL) -> None:
        self.conn = conn

    def messages(self) -> Iterator[tuple[bytes, EmailMessage]]:
        _, data = self.conn.uid("SEARCH", "ALL")
        for uid in data[0].split():
            _, fetched = self.conn.uid("FETCH", uid, "(RFC822)")
            raw = fetched[0][1]
            yield uid, email.message_from_bytes(raw, policy=policy.default)

    def move(self, uid: bytes, folder: str) -> None:
        status, data = self.conn.uid("MOVE", uid.decode(), folder)
        if status != "OK":
            raise imaplib.IMAP4.error(f"MOVE to {folder} failed: {data}")


@contextmanager
def mailbox(settings: Settings) -> Generator[Mailbox]:
    with imaplib.IMAP4_SSL(
        settings.imap_host, ssl_context=ssl.create_default_context()
    ) as conn:
        conn.login(settings.imap_user, settings.imap_password.get_secret_value())
        for folder in (PROCESSED, REJECTED):
            conn.create(folder)
        conn.select("INBOX")
        yield Mailbox(conn)
