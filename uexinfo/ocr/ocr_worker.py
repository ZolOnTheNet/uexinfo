"""Worker OCR en arrière-plan pour les screenshots Star Citizen.

Détecte le type d'écran (mission / terminal), lance l'OCR avec le meilleur
moteur disponible, et stocke le résultat dans ScreenshotDB.

Catégories de missions détectées :
  hauling_stellar      — transport dans un système stellaire
  hauling_interstellar — transport entre systèmes
  salvage              — récupération d'épaves
  bounty_hunter        — primes / fugitifs
  mercenary            — éliminations / mercenariat
  collection           — collecte de ressources
  investigation        — enquête / localisation
  delivery             — livraison directe
  hand_mining          — minage à la main
  pvp                  — missions PvP
  unknown              — non déterminé
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from uexinfo.cache.screenshot_db import ScreenshotDB, ScreenshotEntry

log = logging.getLogger(__name__)

# ── Catégories ────────────────────────────────────────────────────────────────

# Mots-clés dans le TITRE de la mission (minuscules)
_CATEGORY_TITLE: list[tuple[str, list[str]]] = [
    ("salvage",              ["salvage"]),
    ("bounty_hunter",        ["bounty", "fugitive", "wanted"]),
    ("mercenary",            ["elimination", "neutralize", "neutralise",
                              "destroy", "mercenary", "assassinate"]),
    ("investigation",        ["investigation", "locate", "find", "missing",
                              "mystery", "research"]),
    ("delivery",             ["delivery", "courier"]),
    ("hand_mining",          ["mining", "miner"]),
    ("collection",           ["collection"]),
    ("pvp",                  ["pvp", "arena", "combat", "fighting"]),
    ("hauling_interstellar", ["interstellar"]),
    # hauling_stellar détecté en dernier (fallback si "haul" présent)
    ("hauling_stellar",      ["cargo haul", "haul", "stellar"]),
]

# Planètes / systèmes connus pour distinguer stellar vs interstellar
_STANTON_BODIES = {
    "stanton", "crusader", "hurston", "microtech", "arccorp",
    "yela", "cellin", "daymar", "ita", "calliope", "clio", "euterpe",
    "arial", "ita", "magda", "wala",
    # Stations L-points Stanton
    "hur-l1", "hur-l2", "hur-l3", "hur-l4", "hur-l5",
    "cru-l1", "cru-l2", "cru-l3", "cru-l4", "cru-l5",
    "mic-l1", "mic-l2", "mic-l3", "mic-l4", "mic-l5",
    "arc-l1", "arc-l2", "arc-l3", "arc-l4", "arc-l5",
    # Stations et lieux importants de Stanton
    "seraphim", "baijini", "port tressler", "everus harbor",
    "grimhex", "grim hex", "covalex", "orison", "lorville",
    "new babbage", "area18",
    "shallow fields", "beautiful glen", "ambitious dream",
    "port olisar", "cloudview", "revel & york", "cry-astro",
}

_PYRO_BODIES = {
    "pyro", "pyro1", "pyro2", "pyro3", "pyro4", "pyro5", "pyro6",
    "bloom", "orbituary", "checkmate", "ruin station",
    "monox", "terminus",
    "ignis", "vatra", "adir", "fairo", "oretani",
}


def _detect_category(result, ctx=None) -> str:  # result: MissionResult
    """Détermine la catégorie de mission depuis le titre et les objectifs."""
    title = (result.title or "").lower()

    for category, keywords in _CATEGORY_TITLE:
        if any(kw in title for kw in keywords):
            if category == "hauling_stellar":
                if _is_interstellar(result, ctx):
                    return "hauling_interstellar"
            return category

    # Pas de match titre → regarder les objectifs
    obj_text = " ".join(result.objectives).lower()
    if "collect" in obj_text and "deliver" in obj_text:
        if _is_interstellar(result, ctx):
            return "hauling_interstellar"
        return "hauling_stellar"
    if "deliver" in obj_text:
        return "delivery"
    if "collect" in obj_text:
        return "collection"

    return "unknown"


def _is_interstellar(result, ctx=None) -> bool:
    """True si les lieux source/destination appartiennent à des systèmes différents."""
    locations = []
    for o in (result.parsed_objectives or []):
        if o.location:
            locations.append(o.location.lower())
        if o.location_hint:
            locations.append(o.location_hint.lower())

    # Si graph disponible, utiliser les nœuds pour déterminer le système
    if ctx is not None:
        try:
            graph = ctx.cache.transport_graph
            systems_found: set[str] = set()
            for loc in locations:
                node = graph.find_node_by_alias(loc)
                if node and node.star_system:
                    systems_found.add(node.star_system.lower())
            if len(systems_found) > 1:
                return True
            if len(systems_found) == 1:
                return False
        except Exception:
            pass

    # Fallback : détection par mots-clés connus
    has_stanton = any(
        any(b in loc for b in _STANTON_BODIES)
        for loc in locations
    )
    has_pyro = any(
        any(b in loc for b in _PYRO_BODIES)
        for loc in locations
    )
    return has_stanton and has_pyro


# ── Sérialisation ─────────────────────────────────────────────────────────────

def _mission_result_to_dict(mr) -> dict:  # mr: MissionResult
    """Sérialise un MissionResult en dict JSON-compatible."""
    # Sources et destinations uniques (ordre de premier apparition)
    seen_src, seen_dst = set(), set()
    sources, destinations = [], []
    for o in mr.parsed_objectives:
        if o.kind == "collect" and o.location and o.location not in seen_src:
            sources.append(o.location)
            seen_src.add(o.location)
        if o.kind == "deliver" and o.location and o.location not in seen_dst:
            destinations.append(o.location)
            seen_dst.add(o.location)

    objectives = []
    for o in mr.parsed_objectives:
        objectives.append({
            "kind":          o.kind,
            "commodity":     o.commodity,
            "quantity_scu":  o.quantity_scu,
            "location":      o.location,
            "location_hint": o.location_hint,
            "full_location": o.full_location,
            "raw":           o.raw,
        })

    return {
        "title":              mr.title,
        "tab":                mr.tab,
        "reward":             mr.reward,
        "availability":       mr.contract_availability,
        "contracted_by":      mr.contracted_by,
        "sources":            sources,
        "destinations":       destinations,
        "total_scu":          mr.total_scu,
        "objectives":         objectives,
        "blue_text":          mr.blue_text,
        "mission_list":       [{"title": t, "reward_k": r} for t, r in mr.mission_list],
        "timestamp":          mr.timestamp.isoformat(),
    }


def _scan_result_to_dict(sr) -> dict:  # sr: ScanResult
    """Sérialise un ScanResult en dict JSON-compatible."""
    commodities = []
    for c in sr.commodities:
        commodities.append({
            "name":         c.name,
            "quantity":     c.quantity,
            "stock":        c.stock,
            "stock_status": c.stock_status,
            "price":        c.price,
            "in_demand":    c.in_demand,
        })
    return {
        "terminal":    sr.terminal,
        "mode":        sr.mode,
        "validated":   sr.validated,
        "commodities": commodities,
        "timestamp":   sr.timestamp.isoformat(),
    }


# ── Worker OCR ────────────────────────────────────────────────────────────────

class OcrWorker:
    """Thread de fond qui traite les screenshots en attente dans ScreenshotDB.

    Usage :
        worker = OcrWorker(db, ctx)
        worker.on_processed(callback)   # callback(entry: ScreenshotEntry)
        worker.submit(Path("file.jpg"))
        worker.stop()
    """

    def __init__(self, db: ScreenshotDB, ctx=None) -> None:
        self._db:    ScreenshotDB = db
        self._ctx    = ctx
        self._queue: queue.Queue[Path | None] = queue.Queue()
        self._callbacks: list[Callable[[ScreenshotEntry], None]] = []
        self._gap_minutes: int = 60   # mis à jour depuis config
        self._thread = threading.Thread(target=self._run, daemon=True, name="ocr-worker")
        self._thread.start()

    def on_processed(self, cb: Callable[[ScreenshotEntry], None]) -> None:
        self._callbacks.append(cb)

    def set_gap_minutes(self, minutes: int) -> None:
        self._gap_minutes = minutes

    def submit(self, path: Path) -> bool:
        """Soumet un screenshot à traiter. Retourne False si déjà traité."""
        if self._db.is_processed(path.name):
            return False
        self._db.mark_pending(path)
        self._queue.put(path)
        return True

    def submit_many(self, paths: list[Path]) -> int:
        """Soumet plusieurs screenshots. Retourne le nombre effectivement mis en queue."""
        count = 0
        for p in paths:
            if self.submit(p):
                count += 1
        return count

    def qsize(self) -> int:
        """Nombre d'éléments encore en attente dans la queue."""
        return self._queue.qsize()

    def stop(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=5)

    # ── Thread interne ────────────────────────────────────────────────────────

    def _run(self) -> None:
        while True:
            path = self._queue.get()
            if path is None:
                break
            try:
                entry = self._process(path)
                self._db.upsert(entry)
                self._db.save()
                for cb in self._callbacks:
                    try:
                        cb(entry)
                    except Exception:
                        pass
            except Exception as exc:
                log.warning("OcrWorker: erreur traitement %s : %s", path.name, exc)
                # Mettre à jour l'entrée avec l'erreur
                err_entry = self._db.get(path.name)
                if err_entry:
                    err_entry.type   = "unknown"
                    err_entry.errors = [str(exc)]
                    err_entry.processed_at = time.time()
                    self._db.upsert(err_entry)
                    self._db.save()
            finally:
                self._queue.task_done()

    def _process(self, path: Path) -> ScreenshotEntry:
        """Traite un screenshot et retourne l'entrée complétée."""
        from uexinfo.ocr.engine import TesseractEngine

        engine = TesseractEngine()

        # 1. Détection du type d'écran
        screen_type = engine.detect_screen_type(path)

        # 2. OCR selon le type
        data: dict  = {}
        raw:  dict  = {}
        errors: list[str] = []
        entry_type: str   = "unknown"
        category:   str   = "unknown"

        if screen_type == "mission":
            try:
                mr          = engine.extract_mission(path)
                data        = _mission_result_to_dict(mr)
                entry_type  = "mission"
                category    = _detect_category(mr, self._ctx)
            except Exception as exc:
                errors.append(f"extract_mission: {exc}")
                entry_type = "unknown"

        elif screen_type == "terminal":
            try:
                sr = engine.extract_from_image(path)
                if sr is not None:
                    data       = _scan_result_to_dict(sr)
                    entry_type = f"terminal_{sr.mode}"  # terminal_buy / terminal_sell
                    category   = entry_type
                else:
                    entry_type = "unknown"
            except Exception as exc:
                errors.append(f"extract_terminal: {exc}")
                entry_type = "unknown"

        else:
            entry_type = "unknown"

        # 3. Session ID
        try:
            file_mtime = path.stat().st_mtime
        except OSError:
            file_mtime = time.time()

        session_id = self._db.compute_session_id(file_mtime, self._gap_minutes)

        return ScreenshotEntry(
            file         = path.name,
            path         = str(path.resolve()),
            file_mtime   = file_mtime,
            processed_at = time.time(),
            type         = entry_type,
            engine       = "tesseract",
            session_id   = session_id,
            category     = category,
            data         = data,
            raw          = raw,
            errors       = errors,
        )


# ── Helpers publics ────────────────────────────────────────────────────────────

CATEGORY_LABELS: dict[str, str] = {
    "hauling_stellar":      "Hauling · Stellaire",
    "hauling_interstellar": "Hauling · Interstellaire",
    "salvage":              "Récupération",
    "bounty_hunter":        "Chasseur de primes",
    "mercenary":            "Mercenaire",
    "collection":           "Collecte",
    "investigation":        "Enquête",
    "delivery":             "Livraison",
    "hand_mining":          "Minage",
    "pvp":                  "PvP",
    "terminal_buy":         "Terminal · Achat",
    "terminal_sell":        "Terminal · Vente",
    "unknown":              "Inconnu",
    "pending":              "En attente",
}


def category_label(cat: str) -> str:
    return CATEGORY_LABELS.get(cat, cat)
