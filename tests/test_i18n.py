from datetime import timedelta

from babel.messages.pofile import read_po

from signal_bridge.digest import render_digest, render_welcome
from signal_bridge.i18n import LOCALES_DIR, translations

from .test_digest import PARIS, message


def test_catalogs_are_complete():
    po_paths = list(LOCALES_DIR.glob("*/LC_MESSAGES/*.po"))
    assert po_paths
    for po_path in po_paths:
        with po_path.open("rb") as po_file:
            catalog = read_po(po_file)
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
    assert translations("fr_FR").gettext("Signal group") == "Groupe Signal"
    assert translations("de").gettext("Signal group") == "Signal group"


def test_french_digest(group):
    group = group.model_copy(update={"locale": "fr"})
    email = render_digest(
        address="bridge@example.org",
        reply_to="bridge+s3cret@example.org",
        group=group,
        group_name="The Band",
        messages=[message(0, "Salut"), message(1, "Re"), message(2, "Moi", own=True)],
        tz=PARIS,
        read_attachment=lambda _: None,
    )
    assert email["Subject"] == "[The Band] 2 nouveaux messages"
    body = email.get_content()
    assert "14:34 marie (vous)\nMoi" in body
    assert body.endswith("--\nRépondez à cet e-mail pour écrire dans le groupe.\n")


def test_french_welcome(group):
    group = group.model_copy(update={"locale": "fr", "freq": timedelta(hours=6)})
    email = render_welcome(
        address="bridge@example.org", reply_to="bridge+s3cret@example.org", group=group
    )
    assert email["Subject"] == "Groupe Signal par e-mail"
    assert "avec au plus 6\xa0heures d'attente" in email.get_content()
