import json
from pathlib import Path

from signal_bridge.config import Group
from signal_bridge.events import Attachment
from signal_bridge.store import Store

from .conftest import ACCOUNT, GROUP_ID

FIXTURE = Path(__file__).parent / "fixtures" / "receive.jsonl"


def test_real_receive_output(group: Group):
    store = Store(":memory:")
    for line in FIXTURE.read_text().splitlines():
        store.ingest(json.loads(line), ACCOUNT, {GROUP_ID: group})

    pending = store.pending(GROUP_ID)
    assert [(m.author, m.text, m.quote, m.mentions_bot) for m in pending] == [
        ("Paul", "Hey @marie", None, True),
        ("Paul", "Response", "Paul: Hey", False),
        ("Paul", "", None, False),
        ("Paul", "Edited", None, False),
    ]
    assert pending[2].attachments == (
        Attachment(
            filename="signal-2026-10-01-234737.jpeg",
            content_type="image/jpeg",
            id="AAAAAAAAAAAAAAAAAAAA.jpeg",
        ),
    )
    assert store.names()[GROUP_ID] == "The Band"
