"""Normalisation unique des noms saisis, lus par OCR ou venant d'UEX."""
from __future__ import annotations

import re
import unicodedata

_APOS = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "`": "'", "´": "'"})
_SPACES = re.compile(r"\s+")


def norm(text: str | None) -> str:
    """Minuscules, sans accents, apostrophes unifiées, `_` → espace, espaces réduits.

    'E’tam' → "e'tam" ; 'New_Babbage' → 'new babbage' ; '  Área  18 ' → 'area 18'.
    Les tirets et points sont conservés (ARC-L1, notation pointée).
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.translate(_APOS).replace("_", " ").lower()
    return _SPACES.sub(" ", s).strip()
