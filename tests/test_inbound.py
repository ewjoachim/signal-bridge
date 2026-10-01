from email.message import EmailMessage

from signal_bridge.inbound import InboundFile, match_group, parse_inbound

ADDRESS = "bridge@example.org"


def reply(
    body: str,
    *,
    sender: str = "Marie <marie@example.org>",
    to: str = "bridge+s3cret@example.org",
) -> EmailMessage:
    email = EmailMessage()
    email["From"] = sender
    email["To"] = to
    email["Subject"] = "Re: [The Band] 2 new messages"
    email.set_content(body)
    return email


def test_match_group(group):
    assert match_group(reply("hi"), ADDRESS, [group]) == group
    assert (
        match_group(reply("hi", sender="MARIE@example.org"), ADDRESS, [group]) == group
    )
    assert (
        match_group(
            reply("hi", to="Bridge <bridge+S3CRET@example.org>"), ADDRESS, [group]
        )
        == group
    )


def test_match_group_rejects(group):
    assert (
        match_group(reply("hi", sender="mallory@example.org"), ADDRESS, [group]) is None
    )
    assert (
        match_group(reply("hi", to="bridge+wrong@example.org"), ADDRESS, [group])
        is None
    )
    assert match_group(reply("hi", to="bridge@example.org"), ADDRESS, [group]) is None
    assert (
        match_group(reply("hi", to="other+s3cret@example.org"), ADDRESS, [group])
        is None
    )


def test_match_group_cc(group):
    email = reply("hi", to="someone@example.org")
    email["Cc"] = "bridge+s3cret@example.org"
    assert match_group(email, ADDRESS, [group]) == group


def test_strips_quoted_reply_en():
    body = (
        "Sounds good, see you Tuesday!\n\n"
        "On Tue, 6 Oct 2026 at 18:00, The Band <bridge+s3cret@example.org> wrote:\n"
        "> 14:32 Paul\n> Rehearsal moved to 8pm\n"
    )
    assert parse_inbound(reply(body)).text == "Sounds good, see you Tuesday!"


def test_strips_quoted_reply_fr():
    body = (
        "Ok pour moi\n\n"
        "Le mar. 6 oct. 2026 à 18:00, The Band <bridge+s3cret@example.org> a écrit :\n"
        "> 14:32 Paul\n> Rehearsal moved to 8pm\n"
    )
    assert parse_inbound(reply(body)).text == "Ok pour moi"


def test_html_only():
    email = reply("")
    email.set_content("<div>Hello <b>all</b></div><div>See you</div>", subtype="html")
    assert parse_inbound(email).text == "Hello all\nSee you"


def test_attachments():
    email = reply("Here is the score")
    email.add_attachment(
        b"%PDF", maintype="application", subtype="pdf", filename="../score.pdf"
    )
    inbound = parse_inbound(email)
    assert inbound.text == "Here is the score"
    assert inbound.files == (InboundFile(filename="score.pdf", data=b"%PDF"),)
