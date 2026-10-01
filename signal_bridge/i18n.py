import gettext
from functools import cache
from io import BytesIO
from pathlib import Path

from babel import Locale
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

DOMAIN = "signal_bridge"
LOCALES_DIR = Path(__file__).parent / "locales"


@cache
def translations(locale: str) -> gettext.NullTranslations:
    parsed = Locale.parse(locale)
    for candidate in dict.fromkeys([str(parsed), parsed.language]):
        po_path = LOCALES_DIR / candidate / "LC_MESSAGES" / f"{DOMAIN}.po"
        if po_path.exists():
            # Compiled in memory: no .mo build step, no generated files to keep in sync.
            with po_path.open("rb") as po_file:
                catalog = read_po(po_file, locale=candidate)
            mo_file = BytesIO()
            write_mo(mo_file, catalog)
            mo_file.seek(0)
            return gettext.GNUTranslations(mo_file)
    return gettext.NullTranslations()
