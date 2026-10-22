"""Shared Gettext catalog, selected from the process's system language."""
import gettext
import struct
from pathlib import Path

DOMAIN = 'utwebdavbrowser.dkuschinsky'
LOCALE_DIR = Path(__file__).resolve().parent.parent / 'share' / 'locale'


def load_translation(languages=None, localedir=LOCALE_DIR):
    # With languages=None, gettext follows LANGUAGE/LC_ALL/LC_MESSAGES/LANG.
    # A missing or unreadable catalog must never prevent app startup.
    try:
        return gettext.translation(DOMAIN, localedir=str(localedir),
                                   languages=languages, fallback=True)
    except (OSError, EOFError, ValueError, UnicodeError, struct.error):
        return gettext.NullTranslations()


_translation = load_translation()


def tr(message):
    return _translation.gettext(message)
