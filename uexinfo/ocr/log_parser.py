"""Lecture du log SC-Datarunner — Mode A."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from uexinfo.models.scan_result import ScannedCommodity, ScanResult

# Chemin auto-détecté
_DEFAULT_LOG = Path(__file__).parents[2] / "extprg" / "SC-Datarunner-UEX" / "app.log"

RE_COMMODITY = re.compile(
    r"image_processing\.data_extractor - INFO - Extracted commodity: (\{.+\})$"
)
RE_TERMINAL = re.compile(
    r"image_processing\.\w+ - INFO - (?:Matched terminal|terminal_name): ['\"]?([\w][\w\s\-']+)['\"]?"
)
RE_SUBMISSION = re.compile(
    r"data_management\.api - INFO - Data successfully sent to API\. Response: (.+)$"
)


class LogParser:
    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or _DEFAULT_LOG
        self._offset = 0

    def parse_all(self) -> list[ScanResult]:
        """Parse tout le fichier, groupe les commodités par scan (terminal + soumission API)."""
        if not self.log_path.exists():
            return []

        with open(self.log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        return _group_scans(lines)

    def tail_new(self) -> list[ScannedCommodity]:
        """Lit les nouvelles lignes depuis _offset, met à jour _offset."""
        if not self.log_path.exists():
            return []

        with open(self.log_path, encoding="utf-8", errors="replace") as f:
            f.seek(self._offset)
            new_lines = f.readlines()
            self._offset = f.tell()

        results = []
        for line in new_lines:
            c = _parse_commodity_line(line)
            if c:
                results.append(c)
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
                ))
            current_terminal = mt.group(1).strip()
            current_commodities = []
            continue

        # Commodité extraite
        c = _parse_commodity_line(line)
        if c and current_terminal:
            current_commodities.append(c)
            continue

        # Soumission API = fin du scan courant
        if RE_SUBMISSION.search(line):
            if current_terminal and current_commodities:
                results.append(ScanResult(
                    terminal=current_terminal,
                    commodities=list(current_commodities),
                    source="log",
                ))
                current_commodities = []
                # Le terminal persiste (un même terminal peut être scanné plusieurs fois de suite)

    # Flush du dernier scan s'il n'a pas eu de soumission API
    if current_terminal and current_commodities:
        results.append(ScanResult(
            terminal=current_terminal,
            commodities=list(current_commodities),
            source="log",
        ))

    return results
