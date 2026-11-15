"""Two-language user messages.

Code is English; what the CLI prints follows the series language (`series.json` -> "lang"),
overridable with the SERIES_LANG environment variable. Messages are written inline as
T("English text", "Türkçe metin") so the two versions stay next to each other.
"""
import os

_lang = None
SUPPORTED = ("en", "tr")


def set_lang(lang):
    global _lang
    _lang = lang if lang in SUPPORTED else "en"


def lang():
    if os.environ.get("SERIES_LANG") in SUPPORTED:
        return os.environ["SERIES_LANG"]
    return _lang or "en"


def T(en, tr=None):
    """Return the message in the active language (falls back to English)."""
    return tr if (tr is not None and lang() == "tr") else en
