import functools
import gettext
import io
import pathlib

import babel
from babel.messages import mofile, pofile

DOMAIN = "signal_bridge"
LOCALES_DIR = pathlib.Path(__file__).parent / "locales"


@functools.cache
def translations(locale: str) -> gettext.NullTranslations:
    parsed = babel.Locale.parse(locale)
    for candidate in dict.fromkeys([str(parsed), parsed.language]):
        po_path = LOCALES_DIR / candidate / "LC_MESSAGES" / f"{DOMAIN}.po"
        if po_path.exists():
            # Compiled in memory: no .mo build step, no generated files to keep in sync.
            with po_path.open("rb") as po_file:
                catalog = pofile.read_po(po_file, locale=candidate)
            mo_file = io.BytesIO()
            mofile.write_mo(mo_file, catalog)
            mo_file.seek(0)
            return gettext.GNUTranslations(mo_file)
    return gettext.NullTranslations()
