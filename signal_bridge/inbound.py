import hmac
from collections.abc import Iterable
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr
from html.parser import HTMLParser
from pathlib import Path

from mailparser_reply import EmailReplyParser

from signal_bridge.config import Group

RECIPIENT_HEADERS = ("To", "Cc", "Delivered-To", "X-Original-To")
REPLY_LANGUAGES = ["en", "fr", "de", "es", "it", "nl"]
ATTRIBUTION_MAX_LINES = 4


@dataclass(frozen=True)
class InboundFile:
    filename: str
    data: bytes


@dataclass(frozen=True)
class Inbound:
    text: str
    files: tuple[InboundFile, ...]


def match_group(
    email: EmailMessage, address: str, groups: Iterable[Group]
) -> Group | None:
    sender = parseaddr(str(email.get("From", "")))[1].casefold()
    base_local, _, base_domain = address.casefold().partition("@")
    tokens = set()
    for _, recipient in getaddresses(
        [str(v) for h in RECIPIENT_HEADERS for v in email.get_all(h, [])]
    ):
        local, _, domain = recipient.casefold().rpartition("@")
        name, plus, token = local.partition("+")
        if plus and name == base_local and domain == base_domain:
            tokens.add(token)
    for group in groups:
        expected = group.reply_token.get_secret_value().casefold()
        if group.email.casefold() == sender and any(
            hmac.compare_digest(token, expected) for token in tokens
        ):
            return group
    return None


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = frozenset(
        {"p", "div", "br", "li", "tr", "blockquote", "h1", "h2", "h3"}
    )

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    return "".join(extractor.parts)


def strip_trailing_quote(text: str) -> str:
    """Remove a trailing `>` quote and its "X wrote:" line, whatever the language or date format."""
    lines = text.rstrip().split("\n")
    end = len(lines)
    while end and (lines[end - 1].startswith(">") or not lines[end - 1].strip()):
        end -= 1
    if not any(line.startswith(">") for line in lines[end:]):
        return text.strip()
    start = end
    while start and lines[start - 1].strip() and end - start < ATTRIBUTION_MAX_LINES:
        start -= 1
    if end > start and lines[end - 1].rstrip().endswith(":"):
        end = start
    return "\n".join(lines[:end]).strip()


def parse_inbound(email: EmailMessage) -> Inbound:
    body = email.get_body(preferencelist=("plain", "html"))
    text = ""
    if body is not None:
        content = body.get_content()
        if body.get_content_subtype() == "html":
            content = html_to_text(content)
        reply = EmailReplyParser(languages=REPLY_LANGUAGES).parse_reply(text=content)
        text = strip_trailing_quote(reply or "")

    files = []
    for part in email.walk():
        if part is body or part.is_multipart() or not (filename := part.get_filename()):
            continue
        data = part.get_payload(decode=True)
        if isinstance(data, bytes):
            files.append(InboundFile(filename=Path(filename).name, data=data))
    return Inbound(text=text, files=tuple(files))
