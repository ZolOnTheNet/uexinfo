"""Solde du joueur lu sur le terminal de marchandises (« CURRENT BALANCE: ¤11,369,305 AUEC »).

Le montant est en haut à droite de l'écran, sous « CURRENT BALANCE » ; sa position varie avec
l'angle de vue, d'où une zone large où l'on cherche le libellé puis le nombre.

Le symbole ¤ collé devant le montant est lu de façon variable (« ¤ », « H¤ », « m », « W »…)
et parfois comme un chiffre (« 511,369,305 » pour 11,369,305 ; « 538,393,958 » pour 8,393,958).
Avec un caractère non numérique devant le nombre, la lecture est sûre ; sinon, les montants
possibles sont proposés et départagés par le solde connu (`choose`), ou la lecture est écartée.
Vérifié sur 90 captures (août à octobre 2026) : interface d'octobre lue à chaque fois.
"""
from __future__ import annotations

import os
import re

_ZONE = (0.70, 0.04, 0.99, 0.25)
_RE_LABEL = re.compile(r"BALANCE", re.IGNORECASE)
_RE_TOKEN = re.compile(r"\S*\d[\d,.]*\d")
_RE_GROUPED = re.compile(r"^\d{1,3}(?:[,.]\d{3})+$")


def _value(digits: str) -> int | None:
    """Montant d'un nombre groupé par milliers (« 11,369,305 »), None sinon."""
    return int(re.sub(r"[,.]", "", digits)) if _RE_GROUPED.match(digits) else None


def parse_balance(text: str) -> tuple[int | None, list[int]]:
    """(montant sûr, montants possibles) lus dans le texte OCR de la zone du solde.

    Montant sûr : un caractère non numérique (le ¤ mal lu) précède le nombre. Sinon le ¤ a pu
    être lu comme un ou deux chiffres : les montants possibles sont renvoyés (sûr = None).
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines):
        if not _RE_LABEL.search(line):
            continue
        for cand in lines[i + 1:i + 3]:
            m = _RE_TOKEN.search(cand)
            if not m:
                continue
            tok = m.group(0)
            lead = re.match(r"\D*", tok).group(0)
            rest = tok[len(lead):]
            if lead:
                v = _value(rest)
                if v is not None:
                    return v, []
                continue
            alts = [v for v in (_value(rest[1:]), _value(rest[2:]), _value(rest)) if v]
            if alts:
                return None, alts
        break
    return None, []


def choose(sure: int | None, alts: list[int], known: int = 0) -> int | None:
    """Montant retenu : le sûr ; sinon le possible le plus proche du solde connu (à 50 % près)."""
    if sure:
        return sure
    if not alts or not known:
        return None
    best = min(alts, key=lambda v: abs(v - known))
    return best if abs(best - known) <= known * 0.5 else None


def read_balance(engine, img) -> tuple[int | None, list[int]]:
    """Lit le solde sur une image PIL de l'écran du terminal (environ 0,5 s) ; voir `parse_balance`."""
    from PIL import ImageOps
    w, h = img.size
    zone = img.crop((int(w * _ZONE[0]), int(h * _ZONE[1]), int(w * _ZONE[2]), int(h * _ZONE[3])))
    zone = ImageOps.invert(zone.convert("L"))
    env_bak = os.environ.get("TESSDATA_PREFIX")
    os.environ["TESSDATA_PREFIX"] = str(engine.tessdata_dir)
    try:
        text = engine._pt.image_to_string(zone, lang="eng_sc", config="--psm 6 --oem 3",
                                          timeout=engine._timeout)
    finally:
        if env_bak is None:
            os.environ.pop("TESSDATA_PREFIX", None)
        else:
            os.environ["TESSDATA_PREFIX"] = env_bak
    return parse_balance(text)
