"""Offres de contrats lues sans capture d'écran du joueur.

Le joueur passe en **mode scan des offres** (bouton ou `/mission offres on`), ouvre l'écran
Contrats du mobiGlas et clique sur les offres pour les lire, comme d'habitude. Après chaque clic
ou coup de molette, uexinfo prend lui-même des images de l'écran (jeu en fenêtré sans bordure)
jusqu'à ce que le texte ne bouge plus — le jeu l'écrit progressivement, d'autant plus longtemps
qu'il est long —, lit ce qui a changé et remplit le tableau des offres :
- la liste de gauche (titres, montants, minuteurs) quand elle a défilé ;
- le panneau de droite (récompense exacte, objectifs : cargaison, collecte, livraison) au clic.

Garde-fous : rien n'est lu si Star Citizen n'est pas la fenêtre active, ni si l'onglet OFFERS de
l'écran Contrats n'est pas affiché (bouton vert) ; les images restent en mémoire, jamais écrites.

La partie pure (onglet actif, signatures de zones, minuteurs, tableau des offres) est testée sans
écran ; `ContractWatcher` relie souris, capture et OCR.
"""
from __future__ import annotations

import html
import logging
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


# Zones de l'écran Contrats, en fraction de l'image (vérifié en 2560×1440, 2026-10-20 et 2026-10-31).
_OFFERS_TAB = (0.343, 0.095, 0.397, 0.127)     # bouton OFFERS : vert quand l'onglet est actif
_LIST_BOX = (0.075, 0.14, 0.31, 0.835)         # liste des offres (ocr/contract_list.LIST_BOX)
_DETAIL_BOX = (0.34, 0.15, 0.93, 0.60)         # titre, récompense, objectifs
# Colonne de droite (récompense, objectifs) : juge la fin de l'animation du texte. Le titre et le
# centre en sont exclus : un halo lumineux y bouge sans cesse (capture du 2026-11-01).
_TEXT_BOX = (0.64, 0.11, 0.93, 0.73)
_STEP_S = 0.4                                  # intervalle entre deux images pendant l'animation du texte
_SETTLE_MAX_S = 3.0                            # au-delà, on lit l'écran tel quel (le décor transparent bouge toujours)
_STABLE_TOLERANCE = 20                         # points d'empreinte du texte qui peuvent changer entre deux images « identiques »
_IDLE_STOP_S = 20 * 60                         # mode scan arrêté après 20 min sans écran Contrats


# ── Pur ───────────────────────────────────────────────────────────────────────

def _crop(img, box):
    """Zone `box` (fractions) de l'image."""
    w, h = img.size
    return img.crop((int(w * box[0]), int(h * box[1]), int(w * box[2]), int(h * box[3])))


def offers_tab_active(img) -> bool:
    """Vrai si l'image montre l'écran Contrats, onglet OFFERS actif (bouton vert)."""
    from PIL import ImageStat
    r, g, _ = ImageStat.Stat(_crop(img, _OFFERS_TAB).convert("RGB")).mean
    return g - r > 25


_SELECTED_GREEN = 28        # vert (G − R) de la carte cliquée ; ≤ 21 pour les autres (captures du 01/11)


def selected_card(img, cards) -> int | None:
    """Indice de la carte surlignée en vert dans la liste (l'offre affichée à droite), ou None.

    `cards` : cartes lues par `read_contract_list` sur la même liste (positions dans le panneau).
    """
    from PIL import ImageStat
    from uexinfo.ocr.contract_list import LIST_BOX
    if not cards:
        return None
    panel = _crop(img, LIST_BOX).convert("RGB")
    best, best_green = None, _SELECTED_GREEN
    for i, c in enumerate(cards):
        if c.bottom - c.top < 8:
            continue
        r, g, _ = ImageStat.Stat(panel.crop((0, int(c.top), int(panel.width * 0.7), int(c.bottom)))).mean
        if g - r > best_green:
            best, best_green = i, g - r
    return best


_RE_DETAIL_BP = re.compile(r"^[\W_]*[I1l|]?\s*[\[(]?\s*B[P8]\s*[\])]?\s*[1Il|]?\s*")


def signature(img, box) -> bytes:
    """Empreinte grossière d'une zone (32×32 niveaux de gris, 16 niveaux) : change quand le texte change."""
    small = _crop(img, box).convert("L").resize((32, 32))
    return bytes(v // 16 for v in small.tobytes())


_TEXT_LEVEL = 150           # clarté au-dessus de laquelle un pixel compte comme du texte


def text_signature(img, box) -> bytes:
    """Empreinte du texte clair d'une zone (48×48, 4 niveaux) : le fond transparent du mobiGlas,
    plus sombre, bouge sans cesse mais n'y entre pas ; seule l'écriture du texte la change."""
    zone = _crop(img, box).convert("L")
    zone = zone.resize((max(1, zone.width // 3), max(1, zone.height // 3)))
    mask = zone.point(lambda v: 255 if v > _TEXT_LEVEL else 0).resize((48, 48))
    return bytes(v // 64 for v in mask.tobytes())


def difference(a: bytes | None, b: bytes) -> int:
    """Nombre de points qui diffèrent entre deux empreintes (toutes, si `a` est absente)."""
    return len(b) if a is None else sum(x != y for x, y in zip(a, b))


def changed(a: bytes | None, b: bytes, tolerance: int = 40) -> bool:
    """Vrai si deux empreintes diffèrent sur plus de `tolerance` points (le décor du jeu bouge un peu)."""
    return a is None or sum(x != y for x, y in zip(a, b)) > tolerance


_RE_TIMER_PART = re.compile(r"(\d{1,3})\s*([hms])", re.I)


def parse_timer(text: str) -> int | None:
    """« 2h 11m » → 7860 s, « 5m 20s » → 320 ; None si rien de lisible."""
    parts = _RE_TIMER_PART.findall(text or "")
    if not parts or all(u.lower() == "s" for _, u in parts):
        return None                  # secondes seules : heures ou minutes perdues à la lecture
    unit = {"h": 3600, "m": 60, "s": 1}
    return sum(int(n) * unit[u.lower()] for n, u in parts)


@dataclass
class Offer:
    """Une offre vue à l'écran, enrichie du catalogue (scmdb) et, si le joueur l'a ouverte, du détail."""
    title: str
    reward: int | None
    contractor: str = ""
    xp: int | None = None
    blueprint: bool = False
    recognized: bool = False
    mission_type: str = ""
    rank: str = ""
    scu_min: int | None = None
    scu_max: int | None = None
    container: int | None = None
    expires_at: float | None = None
    seen_at: float = 0.0
    objectives: list[str] = field(default_factory=list)    # « 96 SCU Ship Ammunition → NB Int. Spaceport »
    scu: int | None = None                                   # cargaison lue dans le détail (somme des livraisons)
    pickups: list[str] = field(default_factory=list)         # lieux de collecte (détail)
    drops: list[str] = field(default_factory=list)           # lieux de livraison (détail)
    # livraisons du détail : {"commodity", "scu", "pickup", "drop"} (collecte de la même
    # marchandise, ou la seule collecte de l'offre ; None si on ne sait pas)
    legs: list[dict] = field(default_factory=list)
    mission_id: int | None = None                            # contrat pris : mission enregistrée

    @property
    def key(self) -> tuple:
        """Identité d'une offre : titre et montant (deux offres au même titre ont des montants différents)."""
        return (_norm(self.title), round((self.reward or 0) / 1000))

    @property
    def scu_text(self) -> str:
        """Cargaison : lue dans le détail, sinon les bornes du catalogue."""
        if self.scu:
            return f"{self.scu}"
        if self.scu_min and self.scu_max and self.scu_min != self.scu_max:
            return f"{self.scu_min}–{self.scu_max}"
        return f"{self.scu_max or self.scu_min}" if (self.scu_max or self.scu_min) else ""


def _norm(text: str) -> str:
    """Titre comparable (majuscules, sans ponctuation ni « NNN exp. »)."""
    from uexinfo.cache.contract_catalog import normalize
    return normalize(text)


def _other_title(a: str, b: str) -> bool:
    """Vrai si deux titres (normalisés) désignent des contrats différents : chacun a un mot sans
    équivalent dans l'autre (« junior … small » / « rookie … large ») ; une lettre abîmée ou des
    mots en trop d'un seul côté (OCR) ne suffisent pas."""
    from rapidfuzz import fuzz
    wa = [w for w in a.split() if len(w) >= 4 and w.isalpha()]
    wb = [w for w in b.split() if len(w) >= 4 and w.isalpha()]

    def alone(xs, ys):
        return any(all(fuzz.ratio(x, y) < 75 for y in ys) for x in xs)
    return bool(wa and wb) and alone(wa, wb) and alone(wb, wa)


def _pickup_for(deliver, collects) -> str | None:
    """Lieu de collecte d'une livraison : celui de la même marchandise, sinon le seul de l'offre."""
    same = [c.full_location for c in collects
            if c.commodity and deliver.commodity and _norm(c.commodity) in _norm(deliver.commodity)]
    places = list(dict.fromkeys(same or [c.full_location for c in collects]))
    return places[0] if len(places) == 1 else None


def _same_place(read: str, name: str) -> bool:
    """Lieu lu par l'OCR (« Ruin Station above Pyro VI ») et lieu du joueur (« Ruin Station »)
    désignent le même endroit : même nom court (`cargo_lot.place_key`), ou l'un contient l'autre
    (mots entiers, 5 lettres au moins : « pyro » seul ne suffit pas). Comparaison de texte : les lieux des offres ne sont pas
    reliés à un objet (ils viennent de l'OCR), on ne fait que signaler, sans rien enregistrer."""
    from uexinfo.rules.cargo_lot import place_key
    a, b = place_key(read), place_key(name)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 5 and f" {short} " in f" {long_} "


def _offer_marks(o, here: str, there: str) -> tuple[bool, bool]:
    """(collecte à `here`, livraison à `there`) pour une offre dont le détail a été lu."""
    return (bool(here) and any(_same_place(p, here) for p in o.pickups),
            bool(there) and any(_same_place(d, there) for d in o.drops))


def default_board_path() -> Path:
    """Fichier où le tableau des offres est gardé (`<données uexinfo>/offres.json`)."""
    import appdirs
    return Path(appdirs.user_data_dir("uexinfo")) / "offres.json"


class OffersBoard:
    """Offres vues pendant la session, sans doublon, retirées à leur expiration."""

    KEEP_UNTIMED_S = 12 * 3600      # offre sans minuteur lu : oubliée 12 h après avoir été vue

    def __init__(self, path=None):
        """Tableau vide ; `path` : fichier JSON où il est gardé (relu par `load`, écrit par `save`)."""
        self.path = path
        self.offers: dict[tuple, Offer] = {}
        self.cards: list[tuple] = []     # dernière liste lue : (carte, offre ou None), dans l'ordre

    def add_cards(self, results, now: float) -> int:
        """Cartes reconnues (`ContractCatalog.recognize`) → offres ; nombre d'offres nouvelles."""
        new = 0
        self.cards = []
        for r in results:
            card, c = r.card, (r.contract if r.recognized else None)
            if not c and not getattr(card, "reward", None):
                # ni reconnue ni montant : en-tête de groupe (« HAULING PLANETARY ») ou texte de
                # l'overlay lu avec la liste ; garde sa place (carte surlignée), pas d'offre
                self.cards.append((card, None))
                continue
            if not (card.title or c):
                self.cards.append((card, None))
                continue
            secs = parse_timer(getattr(card, "timer", ""))
            offer = Offer(
                title=c.title if c else card.title, reward=r.reward, contractor=card.contractor,
                xp=r.xp, blueprint=card.blueprint or bool(c and c.blueprint), recognized=bool(c),
                mission_type=c.mission_type if c else "", rank=c.rank if c else "",
                scu_min=c.scu_min if c else None, scu_max=c.scu_max if c else None,
                container=c.container if c else None,
                expires_at=now + secs if secs else None, seen_at=now)
            old = self.offers.get(offer.key)
            if old:
                old.seen_at, old.expires_at = now, offer.expires_at or old.expires_at
                self.cards.append((card, old))
            else:
                self.offers[offer.key] = offer
                self.cards.append((card, offer))
                new += 1
        return new

    def add_detail(self, detail, now: float, selected: int | None = None) -> Offer | None:
        """Panneau de droite (`MissionResult`) → objectifs de l'offre correspondante.

        `selected` : indice dans `self.cards` de la carte surlignée (`selected_card`) — c'est elle
        que montre le détail, même titre et montant mal lus (halo). Sans elle : titre et montant.
        """
        from rapidfuzz import fuzz
        raw_title = _RE_DETAIL_BP.sub("", " ".join(str(getattr(detail, "title", "") or "").split()))
        title = _norm(raw_title)
        reward = getattr(detail, "reward", 0) or 0
        if selected is not None and 0 <= selected < len(self.cards):
            card, best = self.cards[selected]
            if best is not None and title and _other_title(title, _norm(best.title)):
                # « Junior … Small Shipment » rattaché à « Rookie … Large Shipment » (journal du
                # 05/11) : la carte surlignée n'est plus celle lue dans la liste
                best, selected = None, None
        if selected is not None and 0 <= selected < len(self.cards):
            card, best = self.cards[selected]
            if best is None and title:
                # carte au titre illisible : l'offre prend le titre du détail
                secs = parse_timer(getattr(card, "timer", ""))
                best = Offer(title=raw_title, reward=card.reward or reward, contractor=card.contractor,
                             xp=card.xp, blueprint=card.blueprint, recognized=False,
                             expires_at=now + secs if secs else None, seen_at=now)
                self.offers[best.key] = best
                self.cards[selected] = (card, best)
            if best is not None:
                if not best.recognized and title and len(title) > len(_norm(best.title)):
                    best.title = raw_title
                if reward and best.reward and abs(reward - best.reward) > 1500:
                    # montant du détail mal lu, la carte (contrôlée par le catalogue) l'emporte :
                    # 67 500 lu 87 500, et un chiffre perdu (258 250 lu 58 250, 510 500 lu 51 050 ;
                    # catalogue scmdb 4.10.2 : 258 250, 363 000, 510 500)
                    reward = 0
                return self._attach(best, detail, reward, now)
        if not title:
            return None
        best, best_score = None, 0.0
        for o in self.offers.values():
            score = fuzz.token_set_ratio(title, _norm(o.title))
            if reward and o.reward:
                # la liste affiche le montant tronqué au millier (55 750 → « 55k »)
                if reward // 1000 == o.reward // 1000 or abs(reward - o.reward) <= 1500:
                    score += 25                              # titre abîmé (halo) mais même montant
                else:
                    score -= 30                              # même titre, autre montant : autre offre
            if score > best_score:
                best, best_score = o, score
        if best is None or best_score < 80:
            return None
        return self._attach(best, detail, reward, now)

    def _attach(self, best: Offer, detail, reward: int, now: float) -> Offer:
        """Montant exact et objectifs du détail → offre."""
        if reward:
            best.reward = reward                              # montant exact (« ¤ 124,000 »)
        lines, total, pickups, drops, legs = [], 0, [], [], []
        objs = getattr(detail, "parsed_objectives", []) or []
        collects = [ob for ob in objs if ob.kind == "collect" and ob.full_location]
        for ob in objs:
            if ob.kind == "deliver":
                qty = f"{ob.quantity_scu} SCU " if ob.quantity_scu else ""
                name = re.sub(r"\s*\([^)]*/\s*scu\)", "", ob.commodity or "", flags=re.I) or "?"
                lines.append(f"{qty}{name} → {ob.full_location or '?'}")
                total += ob.quantity_scu or 0
                if ob.full_location:
                    drops.append(ob.full_location)
                    legs.append({"commodity": name, "scu": ob.quantity_scu or 0,
                                 "pickup": _pickup_for(ob, collects), "drop": ob.full_location})
            elif ob.kind == "collect" and ob.full_location:
                lines.append(f"collecte : {ob.full_location}")
                pickups.append(ob.full_location)
        if lines:
            best.objectives, best.scu = lines, total or best.scu
            best.pickups, best.drops = list(dict.fromkeys(pickups)), list(dict.fromkeys(drops))
            best.legs = legs
        best.seen_at = now
        return best

    def save(self) -> None:
        """Écrit les offres dans `path` (si défini) : une relance d'uexinfo ne perd pas la moisson."""
        if self.path is None:
            return
        import json
        from dataclasses import asdict
        try:
            tmp = Path(self.path).with_suffix(".part")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps([asdict(o) for o in self.offers.values()], ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(self.path)
        except Exception as e:
            log.warning("offres non enregistrées : %s", e)

    def load(self, now: float) -> int:
        """Relit les offres de `path` encore valables ; nombre d'offres reprises."""
        import json
        from dataclasses import fields
        if self.path is None or not Path(self.path).is_file():
            return 0
        try:
            names = {f.name for f in fields(Offer)}
            for d in json.loads(Path(self.path).read_text(encoding="utf-8")):
                o = Offer(**{k: v for k, v in d.items() if k in names})
                if o.expires_at and o.expires_at <= now:
                    continue
                if not o.expires_at and now - (o.seen_at or 0) > self.KEEP_UNTIMED_S:
                    continue
                self.offers[o.key] = o
        except Exception as e:
            log.warning("offres enregistrées illisibles : %s", e)
        return len(self.offers)

    def clear(self) -> int:
        """Vide le tableau (nouvelle série d'offres) ; nombre d'offres retirées."""
        n = len(self.offers)
        self.offers.clear()
        self.cards = []
        return n

    def lot_items(self, now: float) -> list:
        """Offres encore valables → candidates du meilleur lot (`rules/cargo_lot.py`)."""
        from uexinfo.rules.cargo_lot import LotItem
        return [LotItem(key=o.key, title=o.title, reward=o.reward or 0,
                        scu=o.scu or o.scu_max, exact=bool(o.scu), container=o.container,
                        pickups=list(o.pickups), drops=list(o.drops))
                for o in self.rows(now) if not o.mission_id]

    def ordered(self, now: float, here: str = "", there: str = "") -> list[Offer]:
        """Offres dans l'ordre du tableau (numéros de `/mission offres prendre N`) : marquées
        ★ ⚑ d'abord, puis la plus payée."""
        return sorted(self.rows(now), key=lambda o: -sum(_offer_marks(o, here, there)))

    def find(self, title: str, now: float) -> Offer | None:
        """Offre au titre `title` (notification du Game.log), pas encore prise : la plus récente
        dont le détail a été lu en priorité ; None si aucune ne ressemble assez."""
        from rapidfuzz import fuzz
        t = _norm(title)
        scored = [(fuzz.ratio(t, _norm(o.title)), bool(o.legs), o.seen_at, o)
                  for o in self.rows(now) if not o.mission_id]
        scored = [x for x in scored if x[0] >= 88]
        return max(scored, key=lambda x: x[:3])[3] if scored else None

    def rows(self, now: float) -> list[Offer]:
        """Offres encore valables, la plus payée d'abord."""
        live = [o for o in self.offers.values() if not o.expires_at or o.expires_at > now]
        return sorted(live, key=lambda o: -(o.reward or 0))

    def html(self, now: float, here: str = "", there: str = "") -> str:
        """Tableau HTML des offres (encart de l'overlay). `here` / `there` : position et
        destination du joueur (noms de lieux) ; les offres qui collectent ici (★) ou livrent
        là-bas (⚑) sont surlignées et passent en tête, celles qui font les deux d'abord."""
        marks = {id(o): _offer_marks(o, here, there) for o in self.offers.values()}
        rows = self.ordered(now, here, there)
        legend = []
        if here:
            legend.append(f"<span class='mark-here'>★</span> collecte à {html.escape(here)}")
        if there:
            legend.append(f"<span class='mark-there'>⚑</span> livraison à {html.escape(there)}")
        head = (f"<div class='offers-head'>Offres de contrats — {len(rows)} "
                f"<span class='dim'>(clique sur une offre en jeu pour sa destination)</span>"
                f" <span class='cmd-btn' data-cmd='/mission offres lot' title='/mission offres lot'>Meilleur lot</span>"
                f" <span class='cmd-btn' data-cmd='/mission offres lot dest 2' title='/mission offres lot dest 2'>≤ 2 dest.</span>"
                f" <span class='cmd-btn' data-cmd='/mission offres lot dest 3' title='/mission offres lot dest 3'>≤ 3 dest.</span>"
                f" <span class='cmd-btn' data-cmd='/mission offres vider' title='/mission offres vider'>Vider</span>"
                + (f"<div class='dim'>{' · '.join(legend)}</div>" if legend else "") + "</div>")
        if not rows:
            return head
        out = [head, "<table class='offers'><tr><th>N°</th><th>Contrat</th><th>Montant</th><th>SCU</th>"
                     "<th>Caisse</th><th>Rang</th><th>Reste</th><th></th></tr>"]
        for num, o in enumerate(rows, 1):
            left = ""
            if o.expires_at:
                m = max(0, int((o.expires_at - now) // 60))
                left = f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"
            at_here, to_there = marks[id(o)]
            title = (("<span class='mark-here' title='collecte à ta position'>★</span> " if at_here else "")
                     + ("<span class='mark-there' title='livre à ta destination'>⚑</span> " if to_there else "")
                     + html.escape(o.title) + (" <b class='bp'>[BP]</b>" if o.blueprint else ""))
            if o.xp:
                title += f" <span class='dim'>{o.xp} XP</span>"
            if not o.recognized:
                title = f"<span class='dim'>{title} (non reconnu)</span>"
            reward = f"{o.reward:,}".replace(",", " ") if o.reward else "—"
            cls = ("taken" if o.mission_id else "both" if at_here and to_there
                   else "mark" if at_here or to_there else "")
            take = (f"<span class='dim' title='mission #{o.mission_id}'>✔ pris</span>" if o.mission_id else
                    f"<span class='cmd-btn' data-cmd='/mission offres prendre {num}' "
                    f"title='/mission offres prendre {num} : contrat accepté en jeu, à mettre dans le chemin'>Pris</span>")
            out.append(f"<tr{f' class={chr(39)}{cls}{chr(39)}' if cls else ''}><td class='num dim'>{num}</td>"
                       f"<td>{title}</td><td class='num'>{reward}</td><td class='num'>{o.scu_text}</td>"
                       f"<td class='num'>{o.container or ''}</td><td>{html.escape(o.rank)}</td>"
                       f"<td class='num'>{left}</td><td>{take}</td></tr>")
            for line in o.objectives:
                out.append(f"<tr class='obj'><td></td><td colspan='7'>↳ {html.escape(line)}</td></tr>")
        out.append("</table>")
        return "".join(out)


# ── Écran et souris (Windows) ─────────────────────────────────────────────────

def beep(ok: bool = True) -> None:
    """Bip court aigu : offre lue, passer à la suivante ; grave et plus long (`ok=False`) : offre
    lue au raccourci mais non reconnue, réappuyer (Windows)."""
    try:
        import winsound
        winsound.Beep(1200, 90) if ok else winsound.Beep(400, 250)
    except Exception:
        pass


def keep_image(img, folder, keep: int, name: str) -> None:
    """Garde l'image lue pour le dépannage (JPEG, fil à part : la lecture n'attend pas) ; seules
    les `keep` dernières restent dans `folder`."""
    def save():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            img.convert("RGB").save(folder / name, "JPEG", quality=80)
            for old in sorted(folder.glob("offre-*.jpg"))[:-keep]:
                old.unlink(missing_ok=True)
        except Exception as e:
            log.debug("image non gardée : %s", e)
    threading.Thread(target=save, daemon=True, name="contract-keep").start()


def star_citizen_active() -> bool:
    """Vrai si la fenêtre au premier plan est celle de Star Citizen (Windows seulement)."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value.strip() == "Star Citizen"
    except Exception:
        return False


def stable_frame(grab, step: float = _STEP_S, limit: float = _SETTLE_MAX_S,
                 is_current=lambda: True, sleep=time.sleep, trace: list | None = None):
    """Première image identique à la précédente (texte du jeu fini d'écrire) ; None si abandon.

    `grab()` renvoie une image ou None (jeu plus au premier plan) ; `is_current()` devient faux
    quand un nouveau clic relance l'attente. Au bout de `limit` secondes, la dernière image.
    `trace` : reçoit l'écart mesuré entre chaque image et la précédente (journal).
    """
    prev, img, waited = None, None, 0.0
    while waited < limit:
        sleep(step)
        waited += step
        if not is_current():
            return None
        img = grab()
        if img is None:
            return None
        sig = text_signature(img, _TEXT_BOX) + text_signature(img, _LIST_BOX)
        if prev is not None:
            diff = difference(prev, sig)
            if trace is not None:
                trace.append(diff)
            if diff <= _STABLE_TOLERANCE:
                return img
        prev = sig
    return img


class ContractWatcher:
    """Mode scan des offres : après chaque clic ou coup de molette dans l'écran Contrats, attend
    que le texte soit écrit, capture l'écran et met le tableau des offres à jour
    (`on_update(board)`, appelé depuis le thread de lecture)."""

    _HOTKEY_ID = 0x1EF0                     # identifiant RegisterHotKey du raccourci du mode scan

    def __init__(self, engine, catalog, on_update, on_idle_stop=None, on_read=None,
                 hotkey: str = "", read_on_click: bool = True, keep_images: int = 0, images_dir=None,
                 system_fn=None):
        """`engine` : TesseractEngine ; `catalog` : ContractCatalog (ou None : cartes non reconnues) ;
        `on_idle_stop()` : appelé quand le mode s'arrête seul faute d'écran Contrats ;
        `on_read()` : appelé quand la page est entièrement lue (plus aucune image en attente) — le bip."""
        self.engine, self.catalog, self.on_update = engine, catalog, on_update
        self.on_idle_stop, self.on_read = on_idle_stop, on_read
        # Raccourci clavier : l'offre affichée est lue tout de suite, sans attendre la fin de
        # l'animation (le décor transparent bouge toujours) ; même offre deux fois : la dernière gagne.
        self.hotkey, self.read_on_click = hotkey, read_on_click
        # Dépannage : les `keep_images` dernières images lues gardées dans `images_dir` (0 = aucune)
        self.keep_images, self.images_dir = max(0, int(keep_images or 0)), images_dir
        self.system_fn = system_fn          # () → système du joueur (variantes du catalogue)
        self._hotkey_listener = None
        self._last_offer = None             # offre rattachée par la dernière lecture (bip du raccourci)
        self._early_beep = False            # bip du raccourci déjà donné avant la fin de la lecture
        self._did_read = False              # une lecture OCR a eu lieu depuis le dernier bip
        self.board = OffersBoard()
        self._queue: queue.Queue = queue.Queue(maxsize=8)
        self._listener = None
        self._worker: threading.Thread | None = None
        self._gen = 0                       # numéro du dernier clic : une attente plus ancienne s'arrête
        self._last_list: bytes | None = None
        self._last_detail: bytes | None = None
        self._last_seen = 0.0               # dernière image de l'écran Contrats
        self._settle_s = 0.0                # attente de la dernière image (fin de l'animation)
        self._settle_trace: list[int] = []  # écarts mesurés pendant cette attente
        self._scrolls = 0                   # coups de molette reçus
        self._list_scrolls = -1             # coups de molette au moment de la dernière lecture de la liste
        if engine is not None:
            # Tesseract lancé depuis plusieurs fils à la fois : le dossier des modèles reste fixé
            # (chaque lecture le remet puis le restaure ; sans cela, un fil le retirerait à l'autre).
            import os
            os.environ["TESSDATA_PREFIX"] = str(engine.tessdata_dir)
        self._stop = threading.Event()

    @property
    def active(self) -> bool:
        """Vrai si le mode scan est en marche (souris écoutée)."""
        return self._listener is not None

    def start(self) -> None:
        """Passe en mode scan : écoute la souris (pynput), lance le thread de lecture."""
        if self.active:
            return
        log.info("mode scan des offres lancé")
        from pynput import mouse
        self._stop.clear()
        self._last_seen = time.time()
        self._last_list = self._last_detail = None      # tout relire à la reprise
        self._list_scrolls = -1
        self._listener = mouse.Listener(on_click=self._on_click, on_scroll=self._on_scroll)
        self._listener.daemon = True
        self._listener.start()
        if self.hotkey:
            # Écoute bas niveau, comme la souris : la touche n'est pas retirée au jeu (F9 garde sa
            # fonction en vaisseau) ; elle n'agit que si l'écran Contrats est affiché.
            self._hotkey_listener = self._listen_key(self.hotkey)
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._work, daemon=True, name="contract-watch")
            self._worker.start()

    def stop(self) -> None:
        """Quitte le mode scan (le tableau des offres est gardé)."""
        if self.active:
            log.info("mode scan des offres arrêté")
        self._stop.set()
        self._gen += 1
        if self._listener:
            self._listener.stop()
        self._listener = None
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
        self._hotkey_listener = None

    def _listen_key(self, hotkey: str):
        """Écoute du raccourci (pynput, crochet clavier bas niveau) ; None s'il n'a pu être posé."""
        try:
            from pynput import keyboard
            from uexinfo.overlay import _parse_hotkey
            hk = keyboard.HotKey(keyboard.HotKey.parse(_parse_hotkey(hotkey)), self._on_hotkey)
            holder = {}

            def press(k):
                hk.press(holder["l"].canonical(k))

            def release(k):
                hk.release(holder["l"].canonical(k))
            listener = keyboard.Listener(on_press=press, on_release=release)
            holder["l"] = listener
            listener.daemon = True
            listener.start()
            log.info("raccourci %s à l'écoute (agit seulement dans l'écran Contrats)", hotkey)
            return listener
        except Exception as e:
            log.warning("raccourci %s indisponible : %s", hotkey, e)
            return None

    def _on_click(self, x, y, button, pressed) -> None:
        """Clic relâché : lecture une fois le texte affiché (sauf `[contracts] read_on_click = off`)."""
        if not pressed and self.read_on_click:
            self._schedule()

    def _on_hotkey(self) -> None:
        """Raccourci : capture immédiate de l'écran, détail relu même s'il n'a pas changé.
        Ignoré hors de l'écran Contrats (la touche sert alors au jeu)."""
        if not self.active:
            return
        if not star_citizen_active():
            log.info("touche %s ignorée : Star Citizen n'est pas au premier plan", self.hotkey)
            return
        self._gen += 1                      # une attente de clic en cours est abandonnée
        # le crochet clavier bas niveau doit rendre la main tout de suite (sinon le clavier
        # entier attend la capture) : capture et contrôle de l'écran dans un fil à part
        threading.Thread(target=self._capture_now, daemon=True, name="contract-hotkey").start()

    def _capture_now(self) -> None:
        """Capture du raccourci : mise en file si l'écran Contrats est affiché."""
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            if not offers_tab_active(img):
                log.info("touche %s ignorée : écran Contrats (onglet OFFERS) non affiché", self.hotkey)
                return
            self._settle_s, self._settle_trace = 0.0, []
            self._queue.put_nowait((img, time.time(), True))
            log.info("touche %s : offre affichée capturée", self.hotkey)
        except queue.Full:
            pass
        except Exception as e:
            log.warning("capture au raccourci impossible : %s", e)

    def _on_scroll(self, x, y, dx, dy) -> None:
        """Molette : lecture (liste comprise) une fois la liste immobile."""
        self._scrolls += 1
        self._schedule()

    def _schedule(self) -> None:
        """Lance l'attente d'un écran stable si Star Citizen est au premier plan (annule la précédente)."""
        if not star_citizen_active():
            return
        self._gen += 1
        gen = self._gen
        threading.Thread(target=self._settle, args=(gen,), daemon=True).start()

    def _settle(self, gen: int) -> None:
        """Attend la fin de l'animation du texte, puis met l'image en file (jamais écrite sur disque)."""
        from PIL import ImageGrab

        hidden = [0]

        def grab():
            """Image de l'écran principal ; None si le jeu n'est plus au premier plan ou si l'écran
            Contrats n'est pas affiché sur deux images de suite (clic ailleurs dans le jeu)."""
            if not star_citizen_active():
                return None
            img = ImageGrab.grab()
            hidden[0] = 0 if offers_tab_active(img) else hidden[0] + 1
            return None if hidden[0] >= 2 else img
        try:
            t0, trace = time.time(), []
            img = stable_frame(grab, is_current=lambda: gen == self._gen, trace=trace)
            if img is not None:
                self._settle_s, self._settle_trace = time.time() - t0, trace
                self._queue.put_nowait((img, time.time()))
        except queue.Full:
            pass
        except Exception as e:
            log.debug("capture impossible : %s", e)

    def _work(self) -> None:
        """Lit les images en file : liste si elle a changé, détail s'il a changé."""
        while True:
            if self.active and time.time() - self._last_seen > _IDLE_STOP_S:
                self.stop()
                if self.on_idle_stop:
                    self.on_idle_stop()
            try:
                item = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            if not self.active:
                continue
            img, ts, forced = item[0], item[1], (len(item) > 2 and item[2])
            try:
                self._last_offer, self._early_beep = None, False
                if self.keep_images and self.images_dir is not None and offers_tab_active(img):
                    name = time.strftime("offre-%Y%m%d-%H%M%S", time.localtime(ts)) + f"-{int(ts * 1000) % 1000:03d}.jpg"
                    keep_image(img, self.images_dir, self.keep_images, name)
                    log.info("image gardée : %s%s", name, " (touche)" if forced else "")
                if self.process(img, ts, forced):
                    self.on_update(self.board)
                if forced and self._early_beep:
                    pass                            # bip déjà donné pendant la lecture
                elif forced and self.on_read:
                    # raccourci : bip aigu si l'offre est reconnue, grave sinon (réappuyer)
                    self._did_read = False
                    self.on_read(self._last_offer is not None)
                elif self._did_read and self._queue.empty() and self.on_read:
                    self._did_read = False
                    self.on_read(True)
            except Exception as e:
                log.warning("lecture de l'écran Contrats : %s", e)

    def process(self, img, ts: float, forced: bool = False) -> bool:
        """Lit une image de l'écran ; vrai si le tableau a changé. `forced` (raccourci) : détail
        relu même s'il semble inchangé."""
        if not offers_tab_active(img):
            log.info("image ignorée : onglet OFFERS non visible (attente %.1f s)", self._settle_s)
            return False
        self._last_seen = ts
        from concurrent.futures import ThreadPoolExecutor
        updated = False
        # Liste : relue au premier passage et après un coup de molette, pas à chaque clic (la
        # surbrillance de l'offre cliquée change l'image sans changer la liste).
        list_sig = signature(img, _LIST_BOX)
        read_list = self._last_list is None or (
            self._list_scrolls != self._scrolls and changed(self._last_list, list_sig))
        detail_sig = signature(img, _DETAIL_BOX)
        read_detail = forced or changed(self._last_detail, detail_sig)
        if not (read_list or read_detail):
            log.info("rien de nouveau à lire (attente %.1f s)", self._settle_s)
            return False
        self._did_read = True
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=2) as pool:      # Tesseract : un processus par lecture
            f_list = pool.submit(self._read_list, img) if read_list else None
            f_detail = pool.submit(self.engine.extract_mission, img, False) if read_detail else None
            detail = offer = sel = None
            if forced and f_detail is not None:
                # raccourci : le détail est rattaché dès qu'il est lu, bip sans attendre la liste.
                # Liste à relire (molette) : les cartes connues ne sont plus à leur place, le
                # rattachement se fait alors par le titre et le montant.
                self._last_detail = detail_sig
                detail = f_detail.result()
                sel = None if read_list else selected_card(img, [c for c, _ in self.board.cards])
                offer = self.board.add_detail(detail, ts, sel)
                if offer is not None:
                    self._log_detail(detail, sel, offer)
                    self._last_offer, updated = offer, True
                    if self.on_read:
                        self._early_beep = True
                        self.on_read(True)
                    self.on_update(self.board)
            if f_list is not None:
                self._last_list, self._list_scrolls = list_sig, self._scrolls
                results = f_list.result()
                self.board.add_cards(results, ts)
                updated = True
                ok = sum(1 for r in results if r.recognized)
                log.info("liste : %d cartes, %d reconnues", len(results), ok)
                for r in results:
                    c = r.card
                    if r.recognized:
                        log.info("   OK  %s · %s", r.contract.title, c.reward)
                    else:
                        log.info("   NON titre=%r donneur=%r montant=%s xp=%s bp=%s minuteur=%r",
                                 c.title, c.contractor, c.reward, c.xp, c.blueprint, getattr(c, "timer", ""))
            if f_detail is not None and offer is None:
                self._last_detail = detail_sig
                if detail is None:
                    detail = f_detail.result()
                sel = selected_card(img, [c for c, _ in self.board.cards])
                offer = self.board.add_detail(detail, ts, sel)
                self._last_offer = offer
                self._log_detail(detail, sel, offer)
                if offer is not None:
                    updated = True
        log.info("lu en %.1f s après %.1f s d'attente (écarts %s, stable ≤ %d ; liste %s, détail %s)",
                 time.time() - t0, self._settle_s, self._settle_trace, _STABLE_TOLERANCE,
                 "oui" if read_list else "non", "oui" if read_detail else "non")
        return updated

    @staticmethod
    def _log_detail(detail, sel, offer) -> None:
        """Trace du rattachement du détail à une offre."""
        log.info("détail : carte surlignée %s, titre=%r montant=%s → %s (%d objectifs)",
                 "aucune" if sel is None else sel + 1, detail.title, detail.reward,
                 f"{offer.title} · {offer.reward}" if offer else "AUCUNE OFFRE",
                 len(getattr(detail, "parsed_objectives", []) or []))

    def _read_list(self, img) -> list:
        """Cartes de la liste, reconnues dans le catalogue quand il est là."""
        from uexinfo.ocr.contract_list import read_contract_list
        cards = read_contract_list(self.engine, img)
        if self.catalog is not None:
            system = ""
            if self.system_fn is not None:
                try:
                    system = self.system_fn() or ""
                except Exception:
                    system = ""
            return self.catalog.recognize(cards, system=system)
        from uexinfo.cache.contract_catalog import RecognizedContract
        return [RecognizedContract(c, None, 0.0) for c in cards if c.title]
