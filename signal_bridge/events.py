from collections.abc import Mapping
from dataclasses import dataclass

from signal_bridge.config import Group

MENTION_PLACEHOLDER = "￼"
QUOTE_MAX_LENGTH = 200


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    id: str | None = None


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class Edit:
    author_uuid: str
    ts: int
    text: str


@dataclass(frozen=True)
class Delete:
    author_uuid: str
    ts: int


type Event = NewMessage | Edit | Delete


def render_mentions(
    text: str,
    mentions: list[dict],
    account: str,
    bot_name: str,
    names: Mapping[str, str],
) -> str:
    for mention in sorted(mentions, key=lambda m: m["start"], reverse=True):
        if is_bot(mention, account):
            name = bot_name
        else:
            name = names.get(mention.get("uuid", ""), "someone")
        start, end = mention["start"], mention["start"] + mention["length"]
        text = f"{text[:start]}@{name}{text[end:]}"
    return text


def is_bot(mention: dict, account: str) -> bool:
    return account in {mention.get("number"), mention.get("name")}


def parse_attachment(raw: dict) -> Attachment:
    content_type = raw.get("contentType") or "application/octet-stream"
    filename = raw.get("filename") or raw["id"]
    return Attachment(filename=filename, content_type=content_type, id=raw["id"])


def parse_envelope(
    raw: dict, account: str, groups: Mapping[str, Group], names: Mapping[str, str]
) -> Event | None:
    envelope = raw.get("envelope", {})
    author_uuid = envelope.get("sourceUuid")
    if not author_uuid:
        return None

    if edit := envelope.get("editMessage"):
        data = edit.get("dataMessage", {})
        group = groups.get(data.get("groupInfo", {}).get("groupId", ""))
        if group is None:
            return None
        text = render_mentions(
            data.get("message") or "",
            data.get("mentions", []),
            account,
            group.name,
            names,
        )
        return Edit(author_uuid=author_uuid, ts=edit["targetSentTimestamp"], text=text)

    data = envelope.get("dataMessage")
    if not data:
        return None
    group_info = data.get("groupInfo", {})
    group = groups.get(group_info.get("groupId", ""))
    if group is None:
        return None

    if delete := data.get("remoteDelete"):
        return Delete(author_uuid=author_uuid, ts=delete["timestamp"])

    attachments = tuple(parse_attachment(a) for a in data.get("attachments", []))
    if not data.get("message") and not attachments:
        return None

    mentions = data.get("mentions", [])
    text = render_mentions(
        data.get("message") or "", mentions, account, group.name, names
    )

    quote = None
    if raw_quote := data.get("quote"):
        quoted_author = names.get(raw_quote.get("authorUuid", ""), "someone")
        if raw_quote.get("authorNumber") == account:
            quoted_author = group.name
        quoted_text = render_mentions(
            raw_quote.get("text") or "",
            raw_quote.get("mentions", []),
            account,
            group.name,
            names,
        )
        if len(quoted_text) > QUOTE_MAX_LENGTH:
            quoted_text = quoted_text[:QUOTE_MAX_LENGTH] + "…"
        quote = f"{quoted_author}: {quoted_text}"

    return NewMessage(
        group_id=group.group_id,
        group_name=group_info.get("groupName"),
        author_uuid=author_uuid,
        author=envelope.get("sourceName")
        or names.get(author_uuid)
        or envelope.get("sourceNumber")
        or "someone",
        ts=data["timestamp"],
        text=text,
        quote=quote,
        attachments=attachments,
        mentions_bot=any(is_bot(m, account) for m in mentions),
    )
