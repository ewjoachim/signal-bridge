import dataclasses
import datetime
import zoneinfo

from signal_bridge import digest, events, store

PARIS = zoneinfo.ZoneInfo("Europe/Paris")
T0 = datetime.datetime(2026, 10, 6, 14, 32, tzinfo=PARIS)


def message(minutes: int, text: str, **changes: object) -> store.StoredMessage:
    base = store.StoredMessage(
        id=minutes,
        author="Paul",
        ts=int((T0 + datetime.timedelta(minutes=minutes)).timestamp() * 1000),
        text=text,
        quote=None,
        attachments=(),
        mentions_bot=False,
        own=False,
    )
    return dataclasses.replace(base, **changes)


def test_digest_due():
    freq = datetime.timedelta(hours=12)
    assert not digest.digest_due([], freq, T0)
    assert not digest.digest_due(
        [message(0, "mine", own=True)], freq, T0 + datetime.timedelta(days=2)
    )
    assert not digest.digest_due(
        [message(0, "hi")], freq, T0 + datetime.timedelta(hours=11)
    )
    assert digest.digest_due(
        [message(0, "hi")], freq, T0 + datetime.timedelta(hours=12)
    )
    assert digest.digest_due([message(0, "hi", mentions_bot=True)], freq, T0)


def test_render_digest(group):
    messages = [
        message(
            0,
            "Rehearsal moved to 8pm",
            attachments=(events.Attachment("score.pdf", "application/pdf", "abc.pdf"),),
        ),
        message(5, "Works for me", own=True),
        message(
            60 * 12, "See you!", author="Anne", quote="Paul: Rehearsal moved to 8pm"
        ),
    ]
    msg = digest.render_digest(
        address="bridge@example.org",
        reply_to="bridge+s3cret@example.org",
        group=group,
        group_name="The Band",
        messages=messages,
        tz=PARIS,
        thread=[],
        read_attachment=lambda attachment_id: (
            b"%PDF" if attachment_id == "abc.pdf" else None
        ),
    )
    assert msg["Subject"] == "New messages in The Band"
    assert msg["In-Reply-To"] is None
    assert msg["From"] == "The Band <bridge@example.org>"
    assert msg["To"] == "marie@example.org"
    assert msg["Reply-To"] == "bridge+s3cret@example.org"

    body = msg.get_body(preferencelist=("plain",))
    assert body is not None
    assert body.get_content() == (
        "2 new messages\n\n"
        "— Tue 6 Oct —\n\n"
        "14:32 Paul\nRehearsal moved to 8pm\n📎 score.pdf\n\n"
        "14:37 marie (you)\nWorks for me\n\n"
        "— Wed 7 Oct —\n\n"
        "02:32 Anne\n> Paul: Rehearsal moved to 8pm\nSee you!\n\n"
        "--\nReply to this email to post in the group.\n"
    )
    [attachment] = msg.iter_attachments()
    assert attachment.get_filename() == "score.pdf"
    assert attachment.get_content() == b"%PDF"


def test_render_welcome(group):
    msg = digest.render_welcome(
        address="bridge@example.org", reply_to="bridge+s3cret@example.org", group=group
    )
    assert msg["Reply-To"] == "bridge+s3cret@example.org"
    assert "at most every 12 hours" in msg.get_content()


def test_localized_dates(group):
    body = digest.render_body(
        group.model_copy(update={"locale": "fr"}), [message(0, "Salut")], PARIS
    )
    assert body.startswith(
        "1 nouveau message\n\n— mar. 6 oct. —\n\n14:32 Paul\nSalut\n"
    )


def test_digest_threading(group):
    def make_digest(thread: list[str]):
        return digest.render_digest(
            address="bridge@example.org",
            reply_to="bridge+s3cret@example.org",
            group=group,
            group_name="The Band",
            messages=[message(0, "hi")],
            tz=PARIS,
            read_attachment=lambda _: None,
            thread=thread,
        )

    ids = [f"<{n}@example.org>" for n in range(15)]
    msg = make_digest(ids[:2])
    assert msg["In-Reply-To"] == ids[1]
    assert msg["References"] == f"{ids[0]} {ids[1]}"

    references = str(make_digest(ids)["References"]).split()
    assert references[0] == ids[0]
    assert references[-1] == ids[-1]
    assert len(references) == 10
