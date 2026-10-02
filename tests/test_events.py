from signal_bridge import config, events

from . import conftest


def parse(raw: dict, group: config.Group, names: dict | None = None):
    return events.parse_envelope(
        raw, conftest.ACCOUNT, {group.group_id: group}, names or {}
    )


def test_plain_message(group):
    event = parse(
        conftest.envelope(conftest.group_data(message="Rehearsal moved to 8pm")), group
    )
    assert event == events.NewMessage(
        group_id=conftest.GROUP_ID,
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
    data = conftest.group_data(
        message="￼ and ￼: ok?",
        mentions=[
            {"start": 0, "length": 1, "number": conftest.ACCOUNT, "uuid": "uuid-bot"},
            {"start": 6, "length": 1, "uuid": "uuid-anne"},
        ],
    )
    event = parse(conftest.envelope(data), group, names={"uuid-anne": "Anne"})
    assert isinstance(event, events.NewMessage)
    assert event.text == "@marie and @Anne: ok?"
    assert event.mentions_bot


def test_quote(group):
    data = conftest.group_data(
        message="Yes!",
        quote={"id": 1, "authorUuid": "uuid-anne", "text": "Anyone up for Tuesday?"},
    )
    event = parse(conftest.envelope(data), group, names={"uuid-anne": "Anne"})
    assert isinstance(event, events.NewMessage)
    assert event.quote == "Anne: Anyone up for Tuesday?"


def test_attachment_only(group):
    data = conftest.group_data(
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
    event = parse(conftest.envelope(data), group)
    assert isinstance(event, events.NewMessage)
    assert event.attachments == (
        events.Attachment(
            filename="score.pdf", content_type="application/pdf", id="abc.pdf"
        ),
        events.Attachment(filename="def.jpg", content_type="image/jpeg", id="def.jpg"),
    )


def test_edit(group):
    raw = conftest.envelope(
        editMessage={
            "targetSentTimestamp": 42,
            "dataMessage": conftest.group_data(message="fixed"),
        }
    )
    assert parse(raw, group) == events.Edit(
        author_uuid="uuid-paul", ts=42, text="fixed"
    )


def test_delete(group):
    raw = conftest.envelope(conftest.group_data(remoteDelete={"timestamp": 42}))
    assert parse(raw, group) == events.Delete(author_uuid="uuid-paul", ts=42)


def test_ignored(group):
    other_group = conftest.group_data(message="hi")
    other_group["groupInfo"]["groupId"] = "other"
    assert parse(conftest.envelope(other_group), group) is None
    assert (
        parse(conftest.envelope({"timestamp": 1, "message": "direct message"}), group)
        is None
    )
    assert (
        parse(conftest.envelope(conftest.group_data(reaction={"emoji": "👍"})), group)
        is None
    )
    assert parse(conftest.envelope(typingMessage={"action": "STARTED"}), group) is None
