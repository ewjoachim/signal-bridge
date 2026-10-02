import dataclasses
from collections.abc import Mapping

from signal_bridge import config, models

QUOTE_MAX_LENGTH = 200


@dataclasses.dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    id: str | None = None


@dataclasses.dataclass(frozen=True)
class NewMessage:
    group_id: str
    group_name: str | None
    author_uuid: str
    author: str
    ts: int
    text: str
    quote: str | None
    attachments: tuple[Attachment, ...]
    mentions_bot: bool


@dataclasses.dataclass(frozen=True)
class Edit:
    author_uuid: str
    ts: int
    text: str


@dataclasses.dataclass(frozen=True)
class Delete:
    author_uuid: str
    ts: int


type Event = NewMessage | Edit | Delete


def render_mentions(
    text: str,
    mentions: tuple[models.Mention, ...],
    account: str,
    bot_name: str,
    names: Mapping[str, str],
) -> str:
    for mention in sorted(mentions, key=lambda m: m.start, reverse=True):
        name = (
            bot_name
            if is_bot(mention, account)
            else names.get(mention.uuid or "", "someone")
        )
        text = f"{text[: mention.start]}@{name}{text[mention.start + mention.length :]}"
    return text


def is_bot(mention: models.Mention, account: str) -> bool:
    return account in {mention.number, mention.name}


def find_group(
    data: models.DataMessage, groups: Mapping[str, config.Group]
) -> config.Group | None:
    if data.group_info is None or data.group_info.group_id is None:
        return None
    return groups.get(data.group_info.group_id)


def parse_attachment(attachment: models.Attachment) -> Attachment | None:
    if attachment.id is None:
        return None
    return Attachment(
        filename=attachment.filename or attachment.id,
        content_type=attachment.content_type or "application/octet-stream",
        id=attachment.id,
    )


def render_quote(
    quote: models.Quote, account: str, group: config.Group, names: Mapping[str, str]
) -> str:
    author = (
        group.name
        if quote.author_number == account
        else names.get(quote.author_uuid or "", "someone")
    )
    text = render_mentions(quote.text or "", quote.mentions, account, group.name, names)
    if len(text) > QUOTE_MAX_LENGTH:
        text = text[:QUOTE_MAX_LENGTH] + "…"
    return f"{author}: {text}"


def parse_envelope(
    received: models.Received,
    account: str,
    groups: Mapping[str, config.Group],
    names: Mapping[str, str],
) -> Event | None:
    envelope = received.envelope
    author_uuid = envelope.source_uuid
    if not author_uuid:
        return None

    if (edit := envelope.edit_message) and edit.data_message:
        group = find_group(edit.data_message, groups)
        if group is None:
            return None
        text = render_mentions(
            edit.data_message.message or "",
            edit.data_message.mentions,
            account,
            group.name,
            names,
        )
        return Edit(author_uuid=author_uuid, ts=edit.target_sent_timestamp, text=text)

    data = envelope.data_message
    if data is None or (group := find_group(data, groups)) is None:
        return None

    if data.remote_delete:
        return Delete(author_uuid=author_uuid, ts=data.remote_delete.timestamp)

    attachments = tuple(a for raw in data.attachments if (a := parse_attachment(raw)))
    if not data.message and not attachments:
        return None

    return NewMessage(
        group_id=group.group_id,
        group_name=data.group_info.group_name if data.group_info else None,
        author_uuid=author_uuid,
        author=envelope.source_name
        or names.get(author_uuid)
        or envelope.source_number
        or "someone",
        ts=data.timestamp,
        text=render_mentions(
            data.message or "", data.mentions, account, group.name, names
        ),
        quote=render_quote(data.quote, account, group, names) if data.quote else None,
        attachments=attachments,
        mentions_bot=any(is_bot(m, account) for m in data.mentions),
    )
