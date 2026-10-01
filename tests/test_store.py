from signal_bridge.events import Attachment, Delete, Edit, NewMessage
from signal_bridge.store import Store

from .conftest import GROUP_ID


def new_message(ts: int, text: str) -> NewMessage:
    return NewMessage(
        group_id=GROUP_ID,
        group_name="The Band",
        author_uuid="uuid-paul",
        author="Paul",
        ts=ts,
        text=text,
        quote=None,
        attachments=(
            Attachment(
                filename="score.pdf", content_type="application/pdf", id="abc.pdf"
            ),
        ),
        mentions_bot=False,
    )


def test_message_lifecycle():
    store = Store(":memory:")
    store.apply(new_message(1, "first"))
    store.apply(new_message(1, "duplicate delivery"))
    store.apply(new_message(2, "second"))
    store.apply(Edit(author_uuid="uuid-paul", ts=1, text="first, edited"))
    store.apply(Delete(author_uuid="uuid-paul", ts=2))
    store.add_own_message(GROUP_ID, "marie", 3, "my reply", ())

    pending = store.pending(GROUP_ID)
    assert [(m.text, m.own) for m in pending] == [
        ("first, edited", False),
        ("my reply", True),
    ]
    assert pending[0].attachments[0].filename == "score.pdf"

    store.mark_digested(pending)
    assert store.pending(GROUP_ID) == []


def test_names_and_welcome():
    store = Store(":memory:")
    store.remember_name("uuid-paul", "Paul")
    store.remember_name("uuid-paul", "Paulo")
    assert store.names() == {"uuid-paul": "Paulo"}

    assert store.welcomed_email(GROUP_ID) is None
    store.set_welcomed_email(GROUP_ID, "marie@example.org")
    assert store.welcomed_email(GROUP_ID) == "marie@example.org"
