"""Base de données des screenshots capturés.

Stocke les résultats OCR pré-traités pour chaque screenshot SC afin d'éviter
de relancer l'OCR à chaque demande de liste. Persistance JSON atomique.

Fichier : ~/.uexinfo/screenshot_db.json
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Literal

import appdirs

_APP_NAME = "uexinfo"
_DB_PATH  = Path(appdirs.user_data_dir(_APP_NAME)) / "screenshot_db.json"
_VERSION  = "1.0"

# Catégories de missions SC
MissionCategory = Literal[
    "hauling_stellar",
    "hauling_interstellar",
    "salvage",
    "bounty_hunter",
    "mercenary",
    "collection",
    "investigation",
    "delivery",
    "hand_mining",
    "pvp",
    "unknown",
]

ScreenType = Literal["mission", "terminal_buy", "terminal_sell", "terminal", "unknown", "pending"]


@dataclass
class ScreenshotEntry:
    """Entrée dans la base de données screenshots."""
    file:         str            # Nom du fichier (clé, sans chemin)
    path:         str            # Chemin absolu
    file_mtime:   float          # mtime du fichier (stat)
    processed_at: float          # Timestamp traitement OCR
    type:         ScreenType     # Type d'écran détecté
    engine:       str            # "tesseract" | "sc-datarunner" | "none"
    session_id:   str            # "2026-03-21_session1"
    category:     str            # MissionCategory ou "terminal_buy" / "terminal_sell"
    data:         dict           # Données extraites (MissionResult ou ScanResult sérialisé)
    raw:          dict           # OCR brut (debug / re-processing)
    errors:       list[str]      # Erreurs éventuelles

    @property
    def timestamp(self) -> datetime:
        return datetime.fromtimestamp(self.file_mtime)

    @property
    def is_mission(self) -> bool:
        return self.type == "mission"

    @property
    def is_terminal(self) -> bool:
        return self.type in ("terminal_buy", "terminal_sell", "terminal")

    @property
    def is_processed(self) -> bool:
        return self.type != "pending"

    @property
    def title(self) -> str:
        return self.data.get("title", "")

    @property
    def reward(self) -> int:
        return self.data.get("reward", 0)

    @property
    def total_scu(self) -> float:
        return self.data.get("total_scu", 0.0)

    @property
    def sources(self) -> list[str]:
        return self.data.get("sources", [])

    @property
    def destinations(self) -> list[str]:
        return self.data.get("destinations", [])

    def to_dict(self) -> dict:
        return {
            "file":         self.file,
            "path":         self.path,
            "file_mtime":   self.file_mtime,
            "processed_at": self.processed_at,
            "type":         self.type,
            "engine":       self.engine,
            "session_id":   self.session_id,
            "category":     self.category,
            "data":         self.data,
            "raw":          self.raw,
            "errors":       self.errors,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScreenshotEntry":
        return cls(
            file         = d.get("file", ""),
            path         = d.get("path", ""),
            file_mtime   = d.get("file_mtime", 0.0),
            processed_at = d.get("processed_at", 0.0),
            type         = d.get("type", "unknown"),
            engine       = d.get("engine", "none"),
            session_id   = d.get("session_id", ""),
            category     = d.get("category", "unknown"),
            data         = d.get("data", {}),
            raw          = d.get("raw", {}),
            errors       = d.get("errors", []),
        )

    @classmethod
    def pending(cls, path: Path) -> "ScreenshotEntry":
        """Entrée temporaire avant traitement OCR."""
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = time.time()
        return cls(
            file         = path.name,
            path         = str(path),
            file_mtime   = mtime,
            processed_at = 0.0,
            type         = "pending",
            engine       = "none",
            session_id   = "",
            category     = "unknown",
            data         = {},
            raw          = {},
            errors       = [],
        )


class ScreenshotDB:
    """Base de données des screenshots pré-traités.

    Clé : nom de fichier (basename). La base est chargée en mémoire
    et persistée de façon atomique (write tmp → rename).
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path or _DB_PATH
        self._entries: dict[str, ScreenshotEntry] = {}
        self._load()

    # ── Accès ──────────────────────────────────────────────────────────────────

    def has(self, filename: str) -> bool:
        return filename in self._entries

    def is_processed(self, filename: str) -> bool:
        e = self._entries.get(filename)
        return e is not None and e.is_processed

    def get(self, filename: str) -> ScreenshotEntry | None:
        return self._entries.get(filename)

    def all(self) -> list[ScreenshotEntry]:
        return sorted(self._entries.values(), key=lambda e: e.file_mtime)

    # ── Écriture ───────────────────────────────────────────────────────────────

    def upsert(self, entry: ScreenshotEntry) -> None:
        """Insère ou met à jour une entrée (clé = filename)."""
        self._entries[entry.file] = entry

    def upsert_from_result(
        self,
        result,
        image_path: "Path | None" = None,
        gap_minutes: int = 60,
    ) -> ScreenshotEntry:
        """Insère ou met à jour une entrée depuis un ScanResult ou MissionResult.

        Peut être appelé depuis /scan (CLI ou overlay) sans passer par OcrWorker.
        - ScanResult  → type "terminal_buy" | "terminal_sell"
        - MissionResult → type "mission"
        - image_path=None → clé synthétique "log_<terminal>_<ts>" (scans log)
        """
        from uexinfo.models.scan_result import ScanResult
        from uexinfo.models.mission_result import MissionResult

        now = time.time()

        # ── Clé et mtime ─────────────────────────────────────────────────────
        if image_path is not None:
            fname = image_path.name
            try:
                mtime = image_path.stat().st_mtime
            except OSError:
                mtime = now
            path_str = str(image_path.resolve())
        else:
            # Scan log : clé synthétique
            ts_str = result.timestamp.strftime("%Y%m%d_%H%M%S")
            if isinstance(result, ScanResult):
                term = (result.terminal or "unknown").replace(" ", "_")
                fname = f"log_{term}_{ts_str}.log"
            else:
                fname = f"log_mission_{ts_str}.log"
            mtime = result.timestamp.timestamp()
            path_str = ""

        # ── Sérialisation ─────────────────────────────────────────────────────
        if isinstance(result, ScanResult):
            entry_type = f"terminal_{result.mode}"   # "terminal_buy" / "terminal_sell"
            category   = entry_type
            data: dict = {
                "terminal":    result.terminal,
                "mode":        result.mode,
                "validated":   result.validated,
                "source":      getattr(result, "source", "ocr"),
                "commodities": [
                    {
                        "name":         c.name,
                        "quantity":     c.quantity,
                        "stock":        c.stock,
                        "stock_status": c.stock_status,
                        "price":        c.price,
                        "in_demand":    c.in_demand,
                    }
                    for c in result.commodities
                ],
                "timestamp": result.timestamp.isoformat(),
            }
        elif isinstance(result, MissionResult):
            entry_type = "mission"
            category   = "unknown"   # détection fine nécessite le graphe
            data = {
                "title":         result.title,
                "tab":           result.tab,
                "reward":        result.reward,
                "availability":  result.contract_availability,
                "contracted_by": result.contracted_by,
                "sources":       result.all_sources,
                "destinations":  result.all_destinations,
                "total_scu":     result.total_scu,
                "objectives": [
                    {
                        "kind":          o.kind,
                        "commodity":     o.commodity,
                        "quantity_scu":  o.quantity_scu,
                        "location":      o.location,
                        "location_hint": o.location_hint,
                        "raw":           o.raw,
                    }
                    for o in result.parsed_objectives
                ],
                "timestamp": result.timestamp.isoformat(),
            }
        else:
            return None

        session_id = self.compute_session_id(mtime, gap_minutes)

        entry = ScreenshotEntry(
            file         = fname,
            path         = path_str,
            file_mtime   = mtime,
            processed_at = now,
            type         = entry_type,
            engine       = "tesseract",
            session_id   = session_id,
            category     = category,
            data         = data,
            raw          = {},
            errors       = [],
        )
        self._entries[fname] = entry
        return entry

    def mark_pending(self, path: Path) -> ScreenshotEntry:
        """Enregistre un screenshot 'en attente' si inconnu, retourne l'entrée."""
        if path.name not in self._entries:
            entry = ScreenshotEntry.pending(path)
            self._entries[path.name] = entry
            return entry
        return self._entries[path.name]

    # ── Requêtes ───────────────────────────────────────────────────────────────

    def query(
        self,
        since:    float | None = None,
        until:    float | None = None,
        type:     str   | None = None,
        category: str   | None = None,
        session:  str   | None = None,
    ) -> list[ScreenshotEntry]:
        """Retourne les entrées filtrées, triées par mtime croissant."""
        result = []
        for e in self._entries.values():
            if since    is not None and e.file_mtime < since:    continue
            if until    is not None and e.file_mtime > until:    continue
            if type     is not None and e.type != type:          continue
            if category is not None and e.category != category:  continue
            if session  is not None and e.session_id != session: continue
            result.append(e)
        return sorted(result, key=lambda e: e.file_mtime)

    def missions(self, since: float | None = None) -> list[ScreenshotEntry]:
        """Entrées mission seulement."""
        return self.query(since=since, type="mission")

    def terminals(self, since: float | None = None) -> list[ScreenshotEntry]:
        """Entrées terminal seulement."""
        result = []
        for e in self.query(since=since):
            if e.is_terminal:
                result.append(e)
        return result

    def pending_entries(self) -> list[ScreenshotEntry]:
        """Entrées non encore traitées par l'OCR."""
        return [e for e in self._entries.values() if not e.is_processed]

    def session_groups(
        self,
        since:       float,
        gap_minutes: int = 60,
    ) -> list[list[ScreenshotEntry]]:
        """Regroupe les entrées en sessions selon les gaps temporels.

        Un gap > gap_minutes entre deux screenshots consécutifs = nouvelle session.
        Retourne liste de groupes triés par session (plus récente en dernier).
        """
        entries = self.query(since=since)
        if not entries:
            return []

        gap_sec = gap_minutes * 60
        groups: list[list[ScreenshotEntry]] = []
        current: list[ScreenshotEntry] = [entries[0]]

        for e in entries[1:]:
            if e.file_mtime - current[-1].file_mtime > gap_sec:
                groups.append(current)
                current = [e]
            else:
                current.append(e)
        groups.append(current)
        return groups

    def compute_session_id(self, mtime: float, gap_minutes: int = 60) -> str:
        """Calcule le session_id d'un screenshot selon les gaps existants."""
        date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
        gap_sec  = gap_minutes * 60

        # Toutes les entrées du même jour, triées
        same_day = sorted(
            [e for e in self._entries.values()
             if e.file_mtime > 0 and
             datetime.fromtimestamp(e.file_mtime).strftime("%Y-%m-%d") == date_str],
            key=lambda e: e.file_mtime,
        )

        if not same_day:
            return f"{date_str}_session1"

        # Reconstruire les sessions du jour
        sessions: list[tuple[float, float, int]] = []  # (start_mtime, end_mtime, num)
        sess_start = same_day[0].file_mtime
        sess_end   = same_day[0].file_mtime
        sess_num   = 1

        for e in same_day[1:]:
            if e.file_mtime - sess_end > gap_sec:
                sessions.append((sess_start, sess_end, sess_num))
                sess_start = e.file_mtime
                sess_num  += 1
            sess_end = e.file_mtime
        sessions.append((sess_start, sess_end, sess_num))

        # Dans quelle session tombe mtime ?
        for (start, end, num) in sessions:
            if start - gap_sec <= mtime <= end + gap_sec:
                return f"{date_str}_session{num}"

        # Nouveau screenshot après la dernière session connue
        last_num = sessions[-1][2]
        if mtime > sessions[-1][1] + gap_sec:
            return f"{date_str}_session{last_num + 1}"
        return f"{date_str}_session{last_num}"

    # ── Persistance ────────────────────────────────────────────────────────────

    def save(self) -> None:
        """Sauvegarde atomique : écriture tmp → rename."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        payload = {
            "version": _VERSION,
            "entries": {k: v.to_dict() for k, v in self._entries.items()},
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._path)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            for k, v in payload.get("entries", {}).items():
                self._entries[k] = ScreenshotEntry.from_dict(v)
        except Exception:
            # DB corrompue → démarrer vide, l'ancienne sera écrasée au prochain save()
            self._entries = {}

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"<ScreenshotDB {len(self)} entries @ {self._path}>"
