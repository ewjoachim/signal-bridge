from signal_bridge.config import Group
from signal_bridge.events import Attachment, Delete, Edit, NewMessage, parse_envelope

from .conftest import ACCOUNT, GROUP_ID, envelope, group_data


def parse(raw: dict, group: Group, names: dict | None = None):
    return parse_envelope(raw, ACCOUNT, {group.group_id: group}, names or {})


def test_plain_message(group):
    event = parse(envelope(group_data(message="Rehearsal moved to 8pm")), group)
    assert event == NewMessage(
        group_id=GROUP_ID,
        group_name="The Band",
        author_uuid="uuid-paul",
        author="Paul",
        ts=1_790_000_000_000,
        text="Rehearsal moved to 8pm",
        quote=None,
        attachments=(),
        mentions_bot=False,
    )


def test_mentions(group):
    data = group_data(
        message="￼ and ￼: ok?",
        mentions=[
            {"start": 0, "length": 1, "number": ACCOUNT, "uuid": "uuid-bot"},
            {"start": 6, "length": 1, "uuid": "uuid-anne"},
        ],
    )
    event = parse(envelope(data), group, names={"uuid-anne": "Anne"})
    assert isinstance(event, NewMessage)
    assert event.text == "@marie and @Anne: ok?"
    assert event.mentions_bot


def test_quote(group):
    data = group_data(
        message="Yes!",
        quote={"id": 1, "authorUuid": "uuid-anne", "text": "Anyone up for Tuesday?"},
    )
    event = parse(envelope(data), group, names={"uuid-anne": "Anne"})
    assert isinstance(event, NewMessage)
    assert event.quote == "Anne: Anyone up for Tuesday?"


def test_attachment_only(group):
    data = group_data(
        attachments=[
            {
                "id": "abc.pdf",
                "contentType": "application/pdf",
                "filename": "score.pdf",
                "isVoiceNote": False,
            },
            {"id": "def.jpg", "contentType": "image/jpeg", "isVoiceNote": False},
        ]
    )
    event = parse(envelope(data), group)
    assert isinstance(event, NewMessage)
    assert event.attachments == (
        Attachment(filename="score.pdf", content_type="application/pdf", id="abc.pdf"),
        Attachment(filename="def.jpg", content_type="image/jpeg", id="def.jpg"),
    )


def test_edit(group):
    raw = envelope(
        editMessage={
            "targetSentTimestamp": 42,
            "dataMessage": group_data(message="fixed"),
        }
    )
    assert parse(raw, group) == Edit(author_uuid="uuid-paul", ts=42, text="fixed")


def test_delete(group):
    raw = envelope(group_data(remoteDelete={"timestamp": 42}))
    assert parse(raw, group) == Delete(author_uuid="uuid-paul", ts=42)


def test_ignored(group):
    other_group = group_data(message="hi")
    other_group["groupInfo"]["groupId"] = "other"
    assert parse(envelope(other_group), group) is None
    assert parse(envelope({"timestamp": 1, "message": "direct message"}), group) is None
    assert parse(envelope(group_data(reaction={"emoji": "👍"})), group) is None
    assert parse(envelope(typingMessage={"action": "STARTED"}), group) is None
