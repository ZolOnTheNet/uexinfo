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

log = logging.getLogger(__name__)

# Zones de l'écran Contrats, en fraction de l'image (vérifié en 2560×1440, 2026-10-20 et 2026-10-31).
_OFFERS_TAB = (0.343, 0.095, 0.397, 0.127)     # bouton OFFERS : vert quand l'onglet est actif
_LIST_BOX = (0.075, 0.14, 0.31, 0.835)         # liste des offres (ocr/contract_list.LIST_BOX)
_DETAIL_BOX = (0.34, 0.15, 0.93, 0.60)         # titre, récompense, objectifs
_STEP_S = 0.4                                  # intervalle entre deux images pendant l'animation du texte
_SETTLE_MAX_S = 8.0                            # au-delà, on lit l'écran tel quel
_STABLE_TOLERANCE = 12                         # écart d'empreinte admis entre deux images « identiques »
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


def signature(img, box) -> bytes:
    """Empreinte grossière d'une zone (32×32 niveaux de gris, 16 niveaux) : change quand le texte change."""
    small = _crop(img, box).convert("L").resize((32, 32))
    return bytes(v // 16 for v in small.tobytes())


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


class OffersBoard:
    """Offres vues pendant la session, sans doublon, retirées à leur expiration."""

    def __init__(self):
        """Tableau vide."""
        self.offers: dict[tuple, Offer] = {}

    def add_cards(self, results, now: float) -> int:
        """Cartes reconnues (`ContractCatalog.recognize`) → offres ; nombre d'offres nouvelles."""
        new = 0
        for r in results:
            card, c = r.card, (r.contract if r.recognized else None)
            if not (card.title or c):
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
            else:
                self.offers[offer.key] = offer
                new += 1
        return new

    def add_detail(self, detail, now: float) -> Offer | None:
        """Panneau de droite (`MissionResult`) → objectifs de l'offre correspondante (titre, montant)."""
        from rapidfuzz import fuzz
        title = _norm(getattr(detail, "title", ""))
        if not title:
            return None
        reward = getattr(detail, "reward", 0) or 0
        best, best_score = None, 0.0
        for o in self.offers.values():
            score = fuzz.token_set_ratio(title, _norm(o.title))
            if reward and o.reward and abs(reward - o.reward) > max(1500, 0.03 * o.reward):
                score -= 30                                  # même titre, autre montant : autre offre
            if score > best_score:
                best, best_score = o, score
        if best is None or best_score < 80:
            return None
        if reward:
            best.reward = reward                              # montant exact (« ¤ 124,000 »)
        lines, total = [], 0
        for ob in getattr(detail, "parsed_objectives", []) or []:
            if ob.kind == "deliver":
                qty = f"{ob.quantity_scu} SCU " if ob.quantity_scu else ""
                lines.append(f"{qty}{ob.commodity or '?'} → {ob.full_location or '?'}")
                total += ob.quantity_scu or 0
            elif ob.kind == "collect" and ob.full_location:
                lines.append(f"collecte : {ob.full_location}")
        if lines:
            best.objectives, best.scu = lines, total or best.scu
        best.seen_at = now
        return best

    def rows(self, now: float) -> list[Offer]:
        """Offres encore valables, la plus payée d'abord."""
        live = [o for o in self.offers.values() if not o.expires_at or o.expires_at > now]
        return sorted(live, key=lambda o: -(o.reward or 0))

    def html(self, now: float) -> str:
        """Tableau HTML des offres (encart de l'overlay)."""
        rows = self.rows(now)
        head = (f"<div class='offers-head'>Offres de contrats — {len(rows)} "
                f"<span class='dim'>(clique sur une offre en jeu pour sa destination)</span></div>")
        if not rows:
            return head
        out = [head, "<table class='offers'><tr><th>Contrat</th><th>Montant</th><th>SCU</th>"
                     "<th>Caisse</th><th>Rang</th><th>Reste</th></tr>"]
        for o in rows:
            left = ""
            if o.expires_at:
                m = max(0, int((o.expires_at - now) // 60))
                left = f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"
            title = html.escape(o.title) + (" <b class='bp'>[BP]</b>" if o.blueprint else "")
            if o.xp:
                title += f" <span class='dim'>{o.xp} XP</span>"
            if not o.recognized:
                title = f"<span class='dim'>{title} (non reconnu)</span>"
            reward = f"{o.reward:,}".replace(",", " ") if o.reward else "—"
            out.append(f"<tr><td>{title}</td><td class='num'>{reward}</td><td class='num'>{o.scu_text}</td>"
                       f"<td class='num'>{o.container or ''}</td><td>{html.escape(o.rank)}</td>"
                       f"<td class='num'>{left}</td></tr>")
            for line in o.objectives:
                out.append(f"<tr class='obj'><td colspan='6'>↳ {html.escape(line)}</td></tr>")
        out.append("</table>")
        return "".join(out)


# ── Écran et souris (Windows) ─────────────────────────────────────────────────

def beep() -> None:
    """Bip court : la page des offres est lue, on peut cliquer sur la suivante (Windows)."""
    try:
        import winsound
        winsound.Beep(1200, 90)
    except Exception:
        pass


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
                 is_current=lambda: True, sleep=time.sleep):
    """Première image identique à la précédente (texte du jeu fini d'écrire) ; None si abandon.

    `grab()` renvoie une image ou None (jeu plus au premier plan) ; `is_current()` devient faux
    quand un nouveau clic relance l'attente. Au bout de `limit` secondes, la dernière image.
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
        sig = signature(img, _DETAIL_BOX) + signature(img, _LIST_BOX)
        if prev is not None and not changed(prev, sig, _STABLE_TOLERANCE):
            return img
        prev = sig
    return img


class ContractWatcher:
    """Mode scan des offres : après chaque clic ou coup de molette dans l'écran Contrats, attend
    que le texte soit écrit, capture l'écran et met le tableau des offres à jour
    (`on_update(board)`, appelé depuis le thread de lecture)."""

    def __init__(self, engine, catalog, on_update, on_idle_stop=None, on_read=None):
        """`engine` : TesseractEngine ; `catalog` : ContractCatalog (ou None : cartes non reconnues) ;
        `on_idle_stop()` : appelé quand le mode s'arrête seul faute d'écran Contrats ;
        `on_read()` : appelé quand la page est entièrement lue (plus aucune image en attente) — le bip."""
        self.engine, self.catalog, self.on_update = engine, catalog, on_update
        self.on_idle_stop, self.on_read = on_idle_stop, on_read
        self._did_read = False              # une lecture OCR a eu lieu depuis le dernier bip
        self.board = OffersBoard()
        self._queue: queue.Queue = queue.Queue(maxsize=8)
        self._listener = None
        self._worker: threading.Thread | None = None
        self._gen = 0                       # numéro du dernier clic : une attente plus ancienne s'arrête
        self._last_list: bytes | None = None
        self._last_detail: bytes | None = None
        self._last_seen = 0.0               # dernière image de l'écran Contrats
        self._stop = threading.Event()

    @property
    def active(self) -> bool:
        """Vrai si le mode scan est en marche (souris écoutée)."""
        return self._listener is not None

    def start(self) -> None:
        """Passe en mode scan : écoute la souris (pynput), lance le thread de lecture."""
        if self.active:
            return
        from pynput import mouse
        self._stop.clear()
        self._last_seen = time.time()
        self._last_list = self._last_detail = None      # tout relire à la reprise
        self._listener = mouse.Listener(on_click=self._on_click, on_scroll=self._on_scroll)
        self._listener.daemon = True
        self._listener.start()
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._work, daemon=True, name="contract-watch")
            self._worker.start()

    def stop(self) -> None:
        """Quitte le mode scan (le tableau des offres est gardé)."""
        self._stop.set()
        self._gen += 1
        if self._listener:
            self._listener.stop()
        self._listener = None

    def _on_click(self, x, y, button, pressed) -> None:
        """Clic relâché : lecture une fois le texte affiché."""
        if not pressed:
            self._schedule()

    def _on_scroll(self, x, y, dx, dy) -> None:
        """Molette : lecture une fois la liste immobile."""
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

        def grab():
            """Image de l'écran principal ; None si le jeu n'est plus au premier plan."""
            return ImageGrab.grab() if star_citizen_active() else None
        try:
            img = stable_frame(grab, is_current=lambda: gen == self._gen)
            if img is not None:
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
                img, ts = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            if not self.active:
                continue
            try:
                if self.process(img, ts):
                    self.on_update(self.board)
                if self._did_read and self._queue.empty() and self.on_read:
                    self._did_read = False
                    self.on_read()
            except Exception as e:
                log.warning("lecture de l'écran Contrats : %s", e)

    def process(self, img, ts: float) -> bool:
        """Lit une image de l'écran ; vrai si le tableau a changé."""
        if not offers_tab_active(img):
            return False
        self._last_seen = ts
        updated = False
        sig = signature(img, _LIST_BOX)
        if changed(self._last_list, sig):
            self._last_list = sig
            self._did_read = True
            from uexinfo.ocr.contract_list import read_contract_list
            cards = read_contract_list(self.engine, img)
            if self.catalog is not None:
                results = self.catalog.recognize(cards)
            else:
                from uexinfo.cache.contract_catalog import RecognizedContract
                results = [RecognizedContract(c, None, 0.0) for c in cards if c.title]
            self.board.add_cards(results, ts)
            updated = True
        sig = signature(img, _DETAIL_BOX)
        if changed(self._last_detail, sig):
            self._last_detail = sig
            self._did_read = True
            detail = self.engine.extract_mission(img, full=False)
            if self.board.add_detail(detail, ts) is not None:
                updated = True
        return updated
