"""Lecture du log SC-Datarunner — Mode A."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import appdirs

from uexinfo.models.scan_result import ScannedCommodity, ScanResult

# Chemin auto-détecté
_DEFAULT_LOG = Path(__file__).parents[2] / "extprg" / "SC-Datarunner-UEX" / "app.log"

# Fichier d'état persistant : offset par fichier log
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

    def _save_state(self, offset: int, mtime: float) -> None:
        state = self._load_state()
        state[str(self.log_path)] = {"offset": offset, "mtime": mtime}
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)

    def get_offset(self) -> int:
        return self._load_state().get(str(self.log_path), {}).get("offset", 0)

    def reset_offset(self) -> None:
        """Remet l'offset à 0 (forcer la relecture complète au prochain parse_new)."""
        self._save_state(0, 0.0)

    # ── Lecture incrémentale ───────────────────────────────────────────────

    def parse_new(self) -> list[ScanResult]:
        """Lit uniquement les nouvelles lignes depuis le dernier offset sauvegardé.

        L'offset est persisté dans _STATE_FILE.  Si le fichier a été recréé
        (taille < offset sauvegardé), l'offset est remis à 0 automatiquement.
        """
        if not self.log_path.is_file():
            return []

        state_entry = self._load_state().get(str(self.log_path), {})
        saved_offset = state_entry.get("offset", 0)
        saved_mtime  = state_entry.get("mtime", 0.0)

        stat = self.log_path.stat()
        current_mtime = stat.st_mtime
        current_size  = stat.st_size

        # Fichier recréé (nouvelle session SC-Datarunner) → repart de 0
        if current_size < saved_offset or current_mtime < saved_mtime:
            saved_offset = 0

        with open(self.log_path, encoding="utf-8", errors="replace") as f:
            f.seek(saved_offset)
            new_lines = f.readlines()
            new_offset = f.tell()

        self._save_state(new_offset, current_mtime)

        if not new_lines:
            return []

        return _group_scans(new_lines)

    # ── Lecture complète (sans gestion d'état) ────────────────────────────

    def parse_all(self) -> list[ScanResult]:
        """Parse tout le fichier sans modifier l'offset persisté."""
        if not self.log_path.is_file():
            return []

        with open(self.log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        return _group_scans(lines)

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
        name=d.get("name", ""),
        commodity_id=int(d.get("id", 0)),
        quantity=d.get("quantity"),
        stock=d.get("stock", ""),
        stock_status=int(d.get("stock_status", 0)),
        price=int(d.get("price", 0)),
    )


def _group_scans(lines: list[str]) -> list[ScanResult]:
    """Groupe les lignes en ScanResult : un scan = terminal + ses commodités jusqu'à la prochaine soumission API."""
    results: list[ScanResult] = []
    current_terminal = ""
    current_type = "buy"          # "buy" | "sell" tel que détecté par SC-Datarunner
    current_commodities: list[ScannedCommodity] = []

    for line in lines:
        # Nouveau terminal détecté
        mt = RE_TERMINAL.search(line)
        if mt:
            # Si on avait un scan en cours, le clore
            if current_terminal and current_commodities:
                results.append(ScanResult(
                    terminal=current_terminal,
                    commodities=list(current_commodities),
                    source="log",
                    mode=current_type,
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
                    validated=True,   # soumis à UEX = confirmé par l'utilisateur
                ))
                current_commodities = []
                # Le terminal et son type persistent (même terminal scanné plusieurs fois)

    # Flush du dernier scan sans soumission API → non validé (en attente)
    if current_terminal and current_commodities:
        results.append(ScanResult(
            terminal=current_terminal,
            commodities=list(current_commodities),
            source="log",
            mode=current_type,
            validated=False,  # pas encore soumis à UEX
        ))

    return results
