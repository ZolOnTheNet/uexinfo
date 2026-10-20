"""Liste des contrats du mobiGlas (panneau gauche de l'écran Contrats) → cartes.

Chaque carte de la liste contient, à gauche, le titre (sur 1 à 3 lignes, suivi de « NNN EXP. »
quand la traduction PolyToolSC installée par Stelliverse est active) puis le donneur d'ordre, et à
droite la récompense (« 124k ») et le temps restant (« 5m 20s »).

Découpage par la **position** des mots (image_to_data) plutôt que par le texte brut : les lignes
de deux cartes voisines ne se mélangent plus. La reconnaissance du contrat (titre exact, points,
catégorie) est faite ensuite par uexinfo.cache.contract_catalog.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# Panneau gauche (liste), en fraction de l'image — vérifié en 2560×1440 (2026-10-20).
LIST_BOX = (0.075, 0.14, 0.31, 0.835)
_RIGHT_COL = 0.78          # au-delà de 78 % de la largeur du panneau : colonne récompense/minuteur
_SCALE = 2                 # agrandissement avant OCR

_RE_XP = re.compile(r"(\d{2,5})\s*EXP\b\.?", re.I)
_RE_REWARD = re.compile(r"^[^\d]{0,2}(\d{1,4}(?:[.,]\d{1,3})?)\s*[kK]$")
_RE_TIMER = re.compile(r"^\d{1,3}[hms]$")


@dataclass
class ContractCard:
    title: str                     # titre lu (sans la partie « NNN EXP. »)
    xp: int | None = None          # points affichés (traduction Stelliverse), sinon None
    contractor: str = ""           # donneur d'ordre (dernière ligne de la carte)
    reward: int | None = None      # aUEC (« 124k » → 124000), None si non lu
    timer: str = ""                # « 5m 20s »
    raw: str = ""                  # texte complet de la colonne gauche
    top: float = 0.0               # position verticale dans le panneau (px)
    bottom: float = 0.0

    @property
    def has_right_column(self) -> bool:
        return self.reward is not None or bool(self.timer)


def parse_reward(token: str) -> int | None:
    m = _RE_REWARD.match(token.strip())
    if not m:
        return None
    return int(round(float(m.group(1).replace(",", ".")) * 1000))


def _lines(words: list[dict]) -> list[dict]:
    lines: list[dict] = []
    for w in sorted(words, key=lambda w: (w["y"], w["x"])):
        if lines and abs(lines[-1]["y"] - w["y"]) < max(w["h"], 8) * 0.6:
            lines[-1]["w"].append(w)
            lines[-1]["h"] = max(lines[-1]["h"], w["h"])
        else:
            lines.append({"y": w["y"], "h": w["h"], "w": [w]})
    return lines


def cards_from_words(words: list[dict], panel_w: float) -> list[ContractCard]:
    """Mots OCR positionnés {t, x, y, h} (coordonnées du panneau) → cartes, de haut en bas."""
    groups: list[list[dict]] = []
    for ln in _lines(words):
        if groups and ln["y"] - groups[-1][-1]["y"] < ln["h"] * 2.6:
            groups[-1].append(ln)
        else:
            groups.append([ln])

    cards = []
    for g in groups:
        left_lines: list[str] = []
        right: list[str] = []
        for ln in g:
            lw = [w["t"] for w in sorted(ln["w"], key=lambda w: w["x"]) if w["x"] <= panel_w * _RIGHT_COL]
            right += [w["t"] for w in sorted(ln["w"], key=lambda w: w["x"]) if w["x"] > panel_w * _RIGHT_COL]
            if lw:
                left_lines.append(" ".join(lw))
        raw = " ".join(left_lines)
        if not raw.strip():
            continue
        m = _RE_XP.search(raw)
        if m:
            title = raw[:m.start()]
            contractor = raw[m.end():]
        elif len(left_lines) > 1:
            title, contractor = " ".join(left_lines[:-1]), left_lines[-1]
        else:
            title, contractor = raw, ""
        reward = next((r for r in map(parse_reward, right) if r is not None), None)
        timer = " ".join(t for t in right if _RE_TIMER.match(t))
        cards.append(ContractCard(
            title=_clean(title), xp=int(m.group(1)) if m else None, contractor=_clean(contractor),
            reward=reward, timer=timer, raw=raw,
            top=g[0]["y"], bottom=g[-1]["y"] + g[-1]["h"],
        ))
    return cards


def _clean(text: str) -> str:
    text = re.sub(r"^[^A-Za-z0-9<]+", "", text)          # puces, « — », « ¤ » de début
    return re.sub(r"\s+", " ", text).strip(" -.,")


# ── OCR ───────────────────────────────────────────────────────────────────────

def _ocr_words(engine, region, psm: int) -> list[dict]:
    from PIL import ImageOps
    img = ImageOps.invert(region.convert("L"))
    img = img.resize((img.width * _SCALE, img.height * _SCALE))
    env_bak = os.environ.get("TESSDATA_PREFIX")
    os.environ["TESSDATA_PREFIX"] = str(engine.tessdata_dir)
    try:
        d = engine._pt.image_to_data(img, lang="eng_sc", config=f"--psm {psm} --oem 3",
                                     output_type=engine._pt.Output.DICT, timeout=engine._timeout)
    finally:
        if env_bak is None:
            os.environ.pop("TESSDATA_PREFIX", None)
        else:
            os.environ["TESSDATA_PREFIX"] = env_bak
    out = []
    for i, txt in enumerate(d["text"]):
        txt = txt.strip()
        if txt and float(d["conf"][i]) > 20:
            out.append({"t": txt, "x": d["left"][i] / _SCALE, "y": d["top"][i] / _SCALE,
                        "h": d["height"][i] / _SCALE})
    return out


def read_contract_list(engine, img) -> list[ContractCard]:
    """Capture de l'écran Contrats (PIL.Image) → cartes de la liste de gauche."""
    w, h = img.size
    box = (int(w * LIST_BOX[0]), int(h * LIST_BOX[1]), int(w * LIST_BOX[2]), int(h * LIST_BOX[3]))
    panel = img.crop(box)
    cards = cards_from_words(_ocr_words(engine, panel, psm=11), panel.width)
    # Seconde lecture, ciblée, des montants non lus (petits caractères de la colonne de droite).
    for c in cards:
        if c.reward is None and c.raw:
            zone = panel.crop((int(panel.width * 0.74), max(0, int(c.top) - 4),
                               panel.width, int(min(panel.height, c.top + (c.bottom - c.top) * 0.6 + 6))))
            for word in _ocr_words(engine, zone, psm=7):
                r = parse_reward(word["t"])
                if r is not None:
                    c.reward = r
                    break
    return cards
