"""Lecture du log SC-Datarunner — Mode A."""
from __future__ import annotations

import ast
import json
import re
from datetime import datetime
from pathlib import Path

import appdirs

from uexinfo.models.scan_result import ScannedCommodity, ScanResult

# Chemin auto-détecté
_DEFAULT_LOG = Path(__file__).parents[2] / "extprg" / "SC-Datarunner-UEX" / "app.log"

# Fichier d'état persistant : offset + contexte terminal en cours
_STATE_FILE = Path(appdirs.user_data_dir("uexinfo")) / "log_state.json"

RE_COMMODITY = re.compile(
    r"image_processing\.data_extractor - INFO - Extracted commodity: (\{.+\})$"
)
RE_TERMINAL = re.compile(
    r"image_processing\.\w+ - INFO - (?:Matched terminal|terminal_name): ['\"]?([\w][\w\s\-']+)['\"]?"
)
RE_SUBMISSION = re.compile(
    r"data_management\.api - INFO - Data successfully sent to API\. Response: (.+)$"
)
RE_TERMINAL_TYPE = re.compile(
    r"data_extractor - INFO - Determined terminal type: (\w+)"
)
RE_TIMESTAMP = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
)


class LogParser:
    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or _DEFAULT_LOG

    # ── État persistant ────────────────────────────────────────────────────

    def _load_state(self) -> dict:
        if _STATE_FILE.exists():
            try:
                with open(_STATE_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_state(
        self,
        offset: int,
        mtime: float,
        prev_offset: int | None = None,
        last_terminal: str = "",
        last_type: str = "buy",
    ) -> None:
        state = self._load_state()
        entry = state.get(str(self.log_path), {})
        if prev_offset is None:
            prev_offset = entry.get("prev_offset", 0)
        state[str(self.log_path)] = {
            "offset":        offset,
            "mtime":         mtime,
            "prev_offset":   prev_offset,
            "last_terminal": last_terminal,
            "last_type":     last_type,
        }
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)

    def get_offset(self) -> int:
        return self._load_state().get(str(self.log_path), {}).get("offset", 0)

    def reset_offset(self) -> None:
        """Remet l'offset à 0 et efface le contexte terminal sauvegardé."""
        self._save_state(0, 0.0, prev_offset=0, last_terminal="", last_type="buy")

    def undo_offset(self) -> bool:
        """Restaure l'offset avant la dernière lecture (annule le dernier parse_new).

        Retourne True si un prev_offset existait, False sinon.
        """
        entry = self._load_state().get(str(self.log_path), {})
        prev = entry.get("prev_offset", 0)
        current = entry.get("offset", 0)
        if prev >= current:
            return False
        self._save_state(
            prev,
            entry.get("mtime", 0.0),
            prev_offset=0,
            last_terminal="",   # on ne peut pas restaurer le contexte terminal pré-undo
            last_type="buy",
        )
        return True

    # ── Lecture incrémentale ───────────────────────────────────────────────

    def parse_new(self) -> list[ScanResult]:
        """Lit uniquement les nouvelles lignes depuis le dernier offset sauvegardé.

        L'offset et le contexte terminal (last_terminal, last_type) sont persistés
        dans _STATE_FILE pour que le prochain appel reprenne au bon endroit même si
        le terminal n'a pas été re-détecté dans ce batch.

        Si le fichier a été recréé (taille < offset sauvegardé), repart de 0.
        """
        if not self.log_path.is_file():
            return []

        state_entry = self._load_state().get(str(self.log_path), {})
        saved_offset   = state_entry.get("offset", 0)
        saved_mtime    = state_entry.get("mtime", 0.0)
        last_terminal  = state_entry.get("last_terminal", "")
        last_type      = state_entry.get("last_type", "buy")

        stat = self.log_path.stat()
        current_mtime = stat.st_mtime
        current_size  = stat.st_size

        # Fichier recréé (nouvelle session SC-Datarunner) → repart de 0
        if current_size < saved_offset or current_mtime < saved_mtime:
            saved_offset  = 0
            last_terminal = ""
            last_type     = "buy"

        with open(self.log_path, encoding="utf-8", errors="replace") as f:
            f.seek(saved_offset)
            new_lines = f.readlines()
            new_offset = f.tell()

        if not new_lines:
            self._save_state(new_offset, current_mtime, prev_offset=saved_offset,
                             last_terminal=last_terminal, last_type=last_type)
            return []

        results, final_terminal, final_type = _group_scans(
            new_lines,
            initial_terminal=last_terminal,
            initial_type=last_type,
        )

        self._save_state(
            new_offset, current_mtime,
            prev_offset=saved_offset,
            last_terminal=final_terminal,
            last_type=final_type,
        )

        return results

    # ── Lecture complète (sans gestion d'état) ────────────────────────────

    def parse_all(self) -> list[ScanResult]:
        """Parse tout le fichier sans modifier l'offset persisté."""
        if not self.log_path.is_file():
            return []

        with open(self.log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        results, _t, _m = _group_scans(lines)
        return results

    @staticmethod
    def _parse_commodity_line(line: str) -> ScannedCommodity | None:
        return _parse_commodity_line(line)


def _parse_commodity_line(line: str) -> ScannedCommodity | None:
    m = RE_COMMODITY.search(line)
    if not m:
        return None
    try:
        d = ast.literal_eval(m.group(1))
    except (ValueError, SyntaxError):
        return None
    return ScannedCommodity(
        name=d.get("name") or "",
        commodity_id=int(d.get("id") or 0),
        quantity=d.get("quantity"),
        stock=d.get("stock") or "",
        stock_status=int(d.get("stock_status") or 0),
        price=int(d.get("price") or 0),
    )


def _parse_log_timestamp(line: str) -> datetime | None:
    """Extrait le timestamp d'une ligne de log SC-Datarunner."""
    m = RE_TIMESTAMP.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _group_scans(
    lines: list[str],
    initial_terminal: str = "",
    initial_type: str = "buy",
) -> tuple[list[ScanResult], str, str]:
    """Groupe les lignes en ScanResult.

    Reprend depuis initial_terminal/initial_type (état persisté entre deux parse_new).
    Retourne (results, final_terminal, final_type) pour que l'appelant puisse
    sauvegarder l'état courant et reprendre correctement au prochain appel.

    Timestamps : extraits des lignes de log (pas datetime.now()).
    """
    results: list[ScanResult] = []
    current_terminal  = initial_terminal
    current_type      = initial_type
    current_commodities: list[ScannedCommodity] = []
    current_ts: datetime | None = None   # timestamp de la dernière ligne vue

    for line in lines:
        # Mise à jour du timestamp courant (extrait de la ligne)
        ts = _parse_log_timestamp(line)
        if ts:
            current_ts = ts

        # Nouveau terminal détecté
        mt = RE_TERMINAL.search(line)
        if mt:
            # Clore le scan en cours s'il y en a un avec des commodités
            if current_terminal and current_commodities:
                results.append(ScanResult(
                    terminal=current_terminal,
                    commodities=list(current_commodities),
                    source="log",
                    mode=current_type,
                    timestamp=current_ts or datetime.now(),
                ))
            current_terminal = mt.group(1).strip()
            current_type = "buy"
            current_commodities = []
            continue

        # Type de terminal (buy/sell)
        mtype = RE_TERMINAL_TYPE.search(line)
        if mtype:
            current_type = mtype.group(1).lower()
            continue

        # Commodité extraite
        c = _parse_commodity_line(line)
        if c and current_terminal:
            current_commodities.append(c)
            continue

        # Soumission API = fin du scan courant → données validées par l'utilisateur
        if RE_SUBMISSION.search(line):
            if current_terminal and current_commodities:
                results.append(ScanResult(
                    terminal=current_terminal,
                    commodities=list(current_commodities),
                    source="log",
                    mode=current_type,
                    validated=True,
                    timestamp=current_ts or datetime.now(),
                ))
                current_commodities = []
                # Le terminal et son type persistent (même terminal peut être re-scanné)

    # Flush du dernier scan sans soumission API → non validé (en attente)
    if current_terminal and current_commodities:
        results.append(ScanResult(
            terminal=current_terminal,
            commodities=list(current_commodities),
            source="log",
            mode=current_type,
            validated=False,
            timestamp=current_ts or datetime.now(),
        ))
        # Le scan en attente est emis mais le terminal reste "courant"
        # pour le prochain parse_new (qui pourra recevoir la soumission API)

    return results, current_terminal, current_type
