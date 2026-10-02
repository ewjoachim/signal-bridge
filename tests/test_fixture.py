import json
import pathlib

from signal_bridge import config, events, store

from . import conftest

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "receive.jsonl"


def test_real_receive_output(group: config.Group):
    db = store.Store(":memory:")
    for line in FIXTURE.read_text().splitlines():
        db.ingest(json.loads(line), conftest.ACCOUNT, {conftest.GROUP_ID: group})

    pending = db.pending(conftest.GROUP_ID)
    assert [(m.author, m.text, m.quote, m.mentions_bot) for m in pending] == [
        ("Paul", "Hey @marie", None, True),
        ("Paul", "Response", "Paul: Hey", False),
        ("Paul", "", None, False),
        ("Paul", "Edited", None, False),
    ]
    assert pending[2].attachments == (
        events.Attachment(
            filename="signal-2026-10-01-234737.jpeg",
            content_type="image/jpeg",
            id="AAAAAAAAAAAAAAAAAAAA.jpeg",
        ),
    )
    assert db.names()[conftest.GROUP_ID] == "The Band"
