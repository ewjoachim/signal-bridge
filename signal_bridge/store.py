import json
import sqlite3
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from signal_bridge.config import Group
from signal_bridge.events import Attachment, Delete, Edit, NewMessage, parse_envelope

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    group_id TEXT NOT NULL,
    author_uuid TEXT,
    author TEXT NOT NULL,
    ts INTEGER NOT NULL,
    text TEXT NOT NULL,
    quote TEXT,
    attachments TEXT NOT NULL DEFAULT '[]',
    mentions_bot INTEGER NOT NULL DEFAULT 0,
    own INTEGER NOT NULL DEFAULT 0,
    digested INTEGER NOT NULL DEFAULT 0,
    UNIQUE (author_uuid, ts)
);
-- Display names of contacts (by uuid) and groups (by group id).
CREATE TABLE IF NOT EXISTS names (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS welcomed (
    group_id TEXT PRIMARY KEY,
    email TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class StoredMessage:
    id: int
    author: str
    ts: int
    text: str
    quote: str | None
    attachments: tuple[Attachment, ...]
    mentions_bot: bool
    own: bool


class Store:
    def __init__(self, path: Path | str) -> None:
        self.conn = sqlite3.connect(path, autocommit=True)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def remember_name(self, key: str, name: str) -> None:
        self.conn.execute(
            "INSERT INTO names (key, name) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET name = excluded.name",
            (key, name),
        )

    def names(self) -> dict[str, str]:
        return {
            row["key"]: row["name"]
            for row in self.conn.execute("SELECT key, name FROM names")
        }

    def ingest(self, raw: dict, account: str, groups: Mapping[str, Group]) -> None:
        envelope = raw.get("envelope", {})
        if (uuid := envelope.get("sourceUuid")) and (
            name := envelope.get("sourceName")
        ):
            self.remember_name(uuid, name)
        event = parse_envelope(raw, account, groups, self.names())
        if event is None:
            return
        if isinstance(event, NewMessage) and event.group_name:
            self.remember_name(event.group_id, event.group_name)
        self.apply(event)

    def apply(self, event: NewMessage | Edit | Delete) -> None:
        match event:
            case NewMessage():
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO messages
                        (group_id, author_uuid, author, ts, text, quote, attachments, mentions_bot)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.group_id,
                        event.author_uuid,
                        event.author,
                        event.ts,
                        event.text,
                        event.quote,
                        dump_attachments(event.attachments),
                        event.mentions_bot,
                    ),
                )
            case Edit():
                self.conn.execute(
                    "UPDATE messages SET text = ? WHERE author_uuid = ? AND ts = ? AND NOT digested",
                    (event.text, event.author_uuid, event.ts),
                )
            case Delete():
                self.conn.execute(
                    "DELETE FROM messages WHERE author_uuid = ? AND ts = ? AND NOT digested",
                    (event.author_uuid, event.ts),
                )

    def add_own_message(
        self,
        group_id: str,
        author: str,
        ts: int,
        text: str,
        attachments: tuple[Attachment, ...],
    ) -> None:
        self.conn.execute(
            "INSERT INTO messages (group_id, author, ts, text, attachments, own) VALUES (?, ?, ?, ?, ?, 1)",
            (group_id, author, ts, text, dump_attachments(attachments)),
        )

    def pending(self, group_id: str) -> list[StoredMessage]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE group_id = ? AND NOT digested ORDER BY ts",
            (group_id,),
        )
        return [
            StoredMessage(
                id=row["id"],
                author=row["author"],
                ts=row["ts"],
                text=row["text"],
                quote=row["quote"],
                attachments=tuple(
                    Attachment(**a) for a in json.loads(row["attachments"])
                ),
                mentions_bot=bool(row["mentions_bot"]),
                own=bool(row["own"]),
            )
            for row in rows
        ]

    def mark_digested(self, messages: list[StoredMessage]) -> None:
        self.conn.executemany(
            "UPDATE messages SET digested = 1 WHERE id = ?", [(m.id,) for m in messages]
        )

    def welcomed_email(self, group_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT email FROM welcomed WHERE group_id = ?", (group_id,)
        ).fetchone()
        return row["email"] if row else None

    def set_welcomed_email(self, group_id: str, email: str) -> None:
        self.conn.execute(
            "INSERT INTO welcomed (group_id, email) VALUES (?, ?) ON CONFLICT (group_id) DO UPDATE SET email = excluded.email",
            (group_id, email),
        )


def dump_attachments(attachments: tuple[Attachment, ...]) -> str:
    return json.dumps([asdict(a) for a in attachments])
