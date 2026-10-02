import datetime
import email.message
import email.utils
import zoneinfo
from collections.abc import Callable

from babel import dates

from signal_bridge import config, i18n, store

REFERENCES_MAX = 10


def digest_due(
    pending: list[store.StoredMessage], freq: datetime.timedelta, now: datetime.datetime
) -> bool:
    others = [m for m in pending if not m.own]
    if not others:
        return False
    if any(m.mentions_bot for m in others):
        return True
    oldest = datetime.datetime.fromtimestamp(others[0].ts / 1000, tz=now.tzinfo)
    return now - oldest >= freq


def render_body(
    group: config.Group, messages: list[store.StoredMessage], tz: zoneinfo.ZoneInfo
) -> str:
    t = i18n.translations(group.locale)
    count = sum(not m.own for m in messages)
    blocks = [
        t.ngettext("{count} new message", "{count} new messages", count).format(
            count=count
        )
    ]
    current_day = None
    for message in messages:
        when = datetime.datetime.fromtimestamp(message.ts / 1000, tz=tz)
        if (
            day := dates.format_date(when, "EEE d MMM", locale=group.locale)
        ) != current_day:
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
    group: config.Group,
    reply_to: str,
    subject: str,
    body: str,
) -> email.message.EmailMessage:
    msg = email.message.EmailMessage()
    msg["From"] = email.utils.formataddr((display_name, address))
    msg["To"] = group.email
    msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    msg["Message-ID"] = email.utils.make_msgid(domain=address.rpartition("@")[2])
    msg.set_content(body)
    return msg


def render_digest(
    *,
    address: str,
    reply_to: str,
    group: config.Group,
    group_name: str,
    messages: list[store.StoredMessage],
    tz: zoneinfo.ZoneInfo,
    read_attachment: Callable[[str], bytes | None],
    thread: list[str],
) -> email.message.EmailMessage:
    subject = (
        i18n.translations(group.locale)
        .gettext("New messages in {group}")
        .format(group=group_name)
    )
    msg = base_email(
        address=address,
        display_name=group_name,
        group=group,
        reply_to=reply_to,
        subject=subject,
        body=render_body(group, messages, tz),
    )
    if thread:
        msg["In-Reply-To"] = thread[-1]
        msg["References"] = " ".join(
            dict.fromkeys(thread[:1] + thread[-REFERENCES_MAX + 1 :])
        )
    for message in messages:
        for attachment in message.attachments:
            if (
                attachment.id is None
                or (data := read_attachment(attachment.id)) is None
            ):
                continue
            maintype, _, subtype = attachment.content_type.partition("/")
            msg.add_attachment(
                data, maintype=maintype, subtype=subtype, filename=attachment.filename
            )
    return msg


def render_welcome(
    *, address: str, reply_to: str, group: config.Group
) -> email.message.EmailMessage:
    t = i18n.translations(group.locale)
    delay = dates.format_timedelta(group.freq, locale=group.locale)
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
