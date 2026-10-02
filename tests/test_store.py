from signal_bridge import events, store

from . import conftest


def new_message(ts: int, text: str) -> events.NewMessage:
    return events.NewMessage(
        group_id=conftest.GROUP_ID,
        group_name="The Band",
        author_uuid="uuid-paul",
        author="Paul",
        ts=ts,
        text=text,
        quote=None,
        attachments=(
            events.Attachment(
                filename="score.pdf", content_type="application/pdf", id="abc.pdf"
            ),
        ),
        mentions_bot=False,
    )


def test_message_lifecycle():
    db = store.Store(":memory:")
    db.apply(new_message(1, "first"))
    db.apply(new_message(1, "duplicate delivery"))
    db.apply(new_message(2, "second"))
    db.apply(events.Edit(author_uuid="uuid-paul", ts=1, text="first, edited"))
    db.apply(events.Delete(author_uuid="uuid-paul", ts=2))
    db.add_own_message(conftest.GROUP_ID, "marie", 3, "my reply", ())

    pending = db.pending(conftest.GROUP_ID)
    assert [(m.text, m.own) for m in pending] == [
        ("first, edited", False),
        ("my reply", True),
    ]
    assert pending[0].attachments[0].filename == "score.pdf"

    db.mark_digested(pending)
    assert db.pending(conftest.GROUP_ID) == []


def test_names_and_welcome():
    db = store.Store(":memory:")
    db.remember_name("uuid-paul", "Paul")
    db.remember_name("uuid-paul", "Paulo")
    assert db.names() == {"uuid-paul": "Paulo"}

    assert db.welcomed_email(conftest.GROUP_ID) is None
    db.set_welcomed_email(conftest.GROUP_ID, "marie@example.org")
    assert db.welcomed_email(conftest.GROUP_ID) == "marie@example.org"


def test_threads_are_weekly():
    db = store.Store(":memory:")
    db.add_to_thread(conftest.GROUP_ID, "2026-W40", "<a@x>")
    db.add_to_thread(conftest.GROUP_ID, "2026-W40", "<b@x>")
    assert db.thread(conftest.GROUP_ID, "2026-W40") == ["<a@x>", "<b@x>"]
    assert db.thread(conftest.GROUP_ID, "2026-W41") == []
    db.add_to_thread(conftest.GROUP_ID, "2026-W41", "<c@x>")
    assert db.thread(conftest.GROUP_ID, "2026-W41") == ["<c@x>"]
    assert db.thread(conftest.GROUP_ID, "2026-W40") == []
