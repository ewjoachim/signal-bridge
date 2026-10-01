from collections.abc import Callable
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from zoneinfo import ZoneInfo

from babel.dates import format_date, format_timedelta

from signal_bridge.config import Group
from signal_bridge.i18n import translations
from signal_bridge.store import StoredMessage


def digest_due(pending: list[StoredMessage], freq: timedelta, now: datetime) -> bool:
    others = [m for m in pending if not m.own]
    if not others:
        return False
    if any(m.mentions_bot for m in others):
        return True
    oldest = datetime.fromtimestamp(others[0].ts / 1000, tz=now.tzinfo)
    return now - oldest >= freq


def render_body(group: Group, messages: list[StoredMessage], tz: ZoneInfo) -> str:
    t = translations(group.locale)
    blocks = []
    current_day = None
    for message in messages:
        when = datetime.fromtimestamp(message.ts / 1000, tz=tz)
        if (day := format_date(when, "EEE d MMM", locale=group.locale)) != current_day:
            blocks.append(f"— {day} —")
            current_day = day
        author = (
            t.gettext("{name} (you)").format(name=group.name)
            if message.own
            else message.author
        )
        lines = [f"{when:%H:%M} {author}"]
        if message.quote:
            lines.append(f"> {message.quote}")
        if message.text:
            lines.append(message.text)
        lines.extend(f"📎 {a.filename}" for a in message.attachments)
        blocks.append("\n".join(lines))
    blocks.append("--\n" + t.gettext("Reply to this email to post in the group."))
    return "\n\n".join(blocks) + "\n"


def base_email(
    *,
    address: str,
    display_name: str,
    group: Group,
    reply_to: str,
    subject: str,
    body: str,
) -> EmailMessage:
    email = EmailMessage()
    email["From"] = formataddr((display_name, address))
    email["To"] = group.email
    email["Reply-To"] = reply_to
    email["Subject"] = subject
    email["Message-ID"] = make_msgid(domain=address.rpartition("@")[2])
    email.set_content(body)
    return email


def render_digest(
    *,
    address: str,
    reply_to: str,
    group: Group,
    group_name: str,
    messages: list[StoredMessage],
    tz: ZoneInfo,
    read_attachment: Callable[[str], bytes | None],
) -> EmailMessage:
    count = sum(not m.own for m in messages)
    new_messages = translations(group.locale).ngettext(
        "{count} new message", "{count} new messages", count
    )
    subject = f"[{group_name}] " + new_messages.format(count=count)
    email = base_email(
        address=address,
        display_name=group_name,
        group=group,
        reply_to=reply_to,
        subject=subject,
        body=render_body(group, messages, tz),
    )
    for message in messages:
        for attachment in message.attachments:
            if (
                attachment.id is None
                or (data := read_attachment(attachment.id)) is None
            ):
                continue
            maintype, _, subtype = attachment.content_type.partition("/")
            email.add_attachment(
                data, maintype=maintype, subtype=subtype, filename=attachment.filename
            )
    return email


def render_welcome(*, address: str, reply_to: str, group: Group) -> EmailMessage:
    t = translations(group.locale)
    delay = format_timedelta(group.freq, locale=group.locale)
    body = (
        "\n\n".join(
            [
                t.gettext("Hi {name},").format(name=group.name),
                t.gettext("You are now connected to a Signal group by email."),
                t.gettext(
                    "New messages from the group are sent to you together, at most every {delay} "
                    "(right away if someone mentions you)."
                ).format(delay=delay),
                t.gettext(
                    "Reply to those emails, or to this one, to post in the group. "
                    'Your messages appear as "[{name}] …".'
                ).format(name=group.name),
                t.gettext("Attachments work both ways."),
            ]
        )
        + "\n"
    )
    return base_email(
        address=address,
        display_name=t.gettext("Signal group"),
        group=group,
        reply_to=reply_to,
        subject=t.gettext("Signal group by email"),
        body=body,
    )
