import datetime

from babel.messages import pofile

from signal_bridge import digest, i18n

from . import test_digest


def test_catalogs_are_complete():
    po_paths = list(i18n.LOCALES_DIR.glob("*/LC_MESSAGES/*.po"))
    assert po_paths
    for po_path in po_paths:
        with po_path.open("rb") as po_file:
            catalog = pofile.read_po(po_file)
        incomplete = [
            m.id
            for m in catalog
            if m.id
            and (
                m.fuzzy
                or not all(m.string if isinstance(m.string, tuple) else [m.string])
            )
        ]
        assert incomplete == [], po_path


def test_locale_fallbacks():
    assert i18n.translations("fr_FR").gettext("Signal group") == "Groupe Signal"
    assert i18n.translations("de").gettext("Signal group") == "Signal group"


def test_french_digest(group):
    group = group.model_copy(update={"locale": "fr"})
    msg = digest.render_digest(
        address="bridge@example.org",
        reply_to="bridge+s3cret@example.org",
        group=group,
        group_name="The Band",
        messages=[
            test_digest.message(0, "Salut"),
            test_digest.message(1, "Re"),
            test_digest.message(2, "Moi", own=True),
        ],
        tz=test_digest.PARIS,
        read_attachment=lambda _: None,
        thread=[],
    )
    assert msg["Subject"] == "Nouveaux messages dans The Band"
    body = msg.get_content()
    assert body.startswith("2 nouveaux messages\n\n— mar. 6 oct. —\n\n")
    assert "14:34 marie (vous)\nMoi" in body
    assert body.endswith("--\nRépondez à cet e-mail pour écrire dans le groupe.\n")


def test_french_welcome(group):
    group = group.model_copy(
        update={"locale": "fr", "freq": datetime.timedelta(hours=6)}
    )
    msg = digest.render_welcome(
        address="bridge@example.org", reply_to="bridge+s3cret@example.org", group=group
    )
    assert msg["Subject"] == "Groupe Signal par e-mail"
    assert "avec au plus 6\xa0heures d'attente" in msg.get_content()
