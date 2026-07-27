"""Lecture du log SC-Datarunner — Mode A."""
from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict
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
# Nouveau format SC-Datarunner (chaque champ enrobé d'un score de confiance) :
# "Extracted commodity: CommodityData(name=StrConfidence(value='Cobalt',
# confidence=86), id=110, quantity=IntConfidence(value=45, confidence=94),
# stock=StrConfidence(value='low inventory', confidence=100),
# stock_status=IntConfidence(value=3, confidence=100),
# price=IntConfidence(value=10050, confidence=14), examined_words=5)"
# — ce n'est plus un littéral dict Python (ast.literal_eval échoue), vérifié
# sur un vrai log après mise à jour de SC-Datarunner (39 occurrences, format
# stable). RE_COMMODITY (ancien format) reste en repli pour compatibilité.
RE_COMMODITY_V2 = re.compile(
    r"Extracted commodity: CommodityData\("
    r"name=StrConfidence\(value='(?P<name>[^']*)', confidence=(?P<name_conf>\d+)\), "
    r"id=(?P<id>\d+), "
    r"quantity=IntConfidence\(value=(?P<quantity>\d+|None), confidence=(?P<quantity_conf>\d+)\), "
    r"stock=StrConfidence\(value='(?P<stock>[^']*)', confidence=(?P<stock_conf>\d+)\), "
    r"stock_status=IntConfidence\(value=(?P<stock_status>\d+|None), confidence=(?P<stock_status_conf>\d+)\), "
    r"price=IntConfidence\(value=(?P<price>\d+|None), confidence=(?P<price_conf>\d+)\)"
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
        pending_commodities: list[dict] | None = None,
    ) -> None:
        state = self._load_state()
        entry = state.get(str(self.log_path), {})
        if prev_offset is None:
            prev_offset = entry.get("prev_offset", 0)
        if pending_commodities is None:
            pending_commodities = entry.get("pending_commodities", [])
        state[str(self.log_path)] = {
            "offset":              offset,
            "mtime":               mtime,
            "prev_offset":         prev_offset,
            "last_terminal":       last_terminal,
            "last_type":           last_type,
            "pending_commodities": pending_commodities,
        }
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)

    def get_offset(self) -> int:
        return self._load_state().get(str(self.log_path), {}).get("offset", 0)

    def reset_offset(self) -> None:
        """Remet l'offset à 0 et efface le contexte terminal sauvegardé."""
        self._save_state(0, 0.0, prev_offset=0, last_terminal="", last_type="buy",
                         pending_commodities=[])

    def advance_to_end(self) -> None:
        """Avance l'offset persisté à la fin du fichier sans lire le contenu.

        Appelé après parse_all() pour que l'auto-check ne re-traite pas
        les scans déjà affichés explicitement.
        """
        if not self.log_path.is_file():
            return
        stat = self.log_path.stat()
        self._save_state(
            stat.st_size, stat.st_mtime,
            prev_offset=self.get_offset(),
            last_terminal="", last_type="buy",
            pending_commodities=[],
        )

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
            pending_commodities=[],
        )
        return True

    # ── Lecture incrémentale ───────────────────────────────────────────────

    def parse_new(self) -> list[ScanResult]:
        """Lit uniquement les nouvelles lignes depuis le dernier offset sauvegardé.

        L'offset, le contexte terminal (last_terminal, last_type) ET les
        commodités déjà extraites mais pas encore soumises (pending_commodities)
        sont persistés dans _STATE_FILE. Le report des commodités en attente est
        indispensable : l'extraction OCR d'un scan et sa ligne de soumission
        arrivent souvent dans deux appels parse_new() distincts (le temps que
        l'utilisateur valide dans Datarunner) — sans ce report, la soumission
        arrive dans un batch sans commodités en mémoire et le scan n'est jamais
        marqué validé.

        Si le fichier a été recréé (taille < offset sauvegardé), repart de 0.
        """
        if not self.log_path.is_file():
            return []

        state_entry = self._load_state().get(str(self.log_path), {})
        saved_offset   = state_entry.get("offset", 0)
        saved_mtime    = state_entry.get("mtime", 0.0)
        last_terminal  = state_entry.get("last_terminal", "")
        last_type      = state_entry.get("last_type", "buy")
        pending_dicts  = state_entry.get("pending_commodities", []) or []

        stat = self.log_path.stat()
        current_mtime = stat.st_mtime
        current_size  = stat.st_size

        # Fichier recréé (nouvelle session SC-Datarunner) → repart de 0
        if current_size < saved_offset or current_mtime < saved_mtime:
            saved_offset  = 0
            last_terminal = ""
            last_type     = "buy"
            pending_dicts = []

        with open(self.log_path, encoding="utf-8", errors="replace") as f:
            f.seek(saved_offset)
            new_lines = f.readlines()
            new_offset = f.tell()

        if not new_lines:
            self._save_state(new_offset, current_mtime, prev_offset=saved_offset,
                             last_terminal=last_terminal, last_type=last_type,
                             pending_commodities=pending_dicts)
            return []

        pending_commodities = [ScannedCommodity(**d) for d in pending_dicts]

        results, final_terminal, final_type, final_commodities = _group_scans(
            new_lines,
            initial_terminal=last_terminal,
            initial_type=last_type,
            initial_commodities=pending_commodities,
        )

        self._save_state(
            new_offset, current_mtime,
            prev_offset=saved_offset,
            last_terminal=final_terminal,
            last_type=final_type,
            pending_commodities=[asdict(c) for c in final_commodities],
        )

        return results

    # ── Lecture complète (sans gestion d'état) ────────────────────────────

    def parse_all(self) -> list[ScanResult]:
        """Parse tout le fichier sans modifier l'offset persisté."""
        if not self.log_path.is_file():
            return []

        with open(self.log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        results, _t, _m, _c = _group_scans(lines)
        return results

    @staticmethod
    def _parse_commodity_line(line: str) -> ScannedCommodity | None:
        return _parse_commodity_line(line)


def _parse_commodity_line(line: str) -> ScannedCommodity | None:
    m2 = RE_COMMODITY_V2.search(line)
    if m2:
        def _int_or(v, default=0):
            return default if v == "None" else int(v)
        # Le format distingue la confiance du texte "stock" (StrConfidence) de
        # celle du niveau numérique stock_status (IntConfidence) — un seul champ
        # affiché côté uexinfo, donc la plus basse des deux.
        stock_confidence = min(int(m2.group("stock_conf")), int(m2.group("stock_status_conf")))
        return ScannedCommodity(
            name=m2.group("name") or "",
            commodity_id=_int_or(m2.group("id")),
            quantity=_int_or(m2.group("quantity"), None),
            stock=m2.group("stock") or "",
            stock_status=_int_or(m2.group("stock_status")),
            price=_int_or(m2.group("price")),
            name_confidence=int(m2.group("name_conf")),
            quantity_confidence=int(m2.group("quantity_conf")),
            stock_confidence=stock_confidence,
            price_confidence=int(m2.group("price_conf")),
        )

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
    initial_commodities: list[ScannedCommodity] | None = None,
) -> tuple[list[ScanResult], str, str, list[ScannedCommodity]]:
    """Groupe les lignes en ScanResult.

    Reprend depuis initial_terminal/initial_type/initial_commodities (état
    persisté entre deux parse_new). Retourne (results, final_terminal,
    final_type, final_commodities) pour que l'appelant puisse sauvegarder
    l'état courant et reprendre correctement au prochain appel.

    initial_commodities est indispensable : l'extraction OCR d'un scan et sa
    ligne de soumission ("Data successfully sent to API") arrivent souvent
    dans deux appels parse_new() distincts (le temps que l'utilisateur
    corrige/valide dans Datarunner). Sans le report des commodités en attente
    d'un appel à l'autre, la ligne de soumission arrive dans un batch où
    current_commodities repart vide — la condition "if current_commodities"
    échoue silencieusement et le scan n'est JAMAIS marqué validated=True.

    Timestamps : extraits des lignes de log (pas datetime.now()).
    """
    results: list[ScanResult] = []
    current_terminal  = initial_terminal
    current_type      = initial_type
    current_commodities: list[ScannedCommodity] = list(initial_commodities or [])
    current_ts: datetime | None = None   # timestamp de la dernière ligne vue

    def _flush_pending(ts_for_flush: datetime | None) -> None:
        if current_terminal and current_commodities:
            results.append(ScanResult(
                terminal=current_terminal,
                commodities=list(current_commodities),
                source="log",
                mode=current_type,
                timestamp=ts_for_flush or datetime.now(),
            ))

    for line in lines:
        # Mise à jour du timestamp courant (extrait de la ligne)
        ts = _parse_log_timestamp(line)
        if ts:
            current_ts = ts

        # Nouveau terminal détecté
        mt = RE_TERMINAL.search(line)
        if mt:
            new_terminal = mt.group(1).strip()
            if new_terminal.lower() != current_terminal.lower():
                # Changement réel de terminal — clore le lot en cours.
                _flush_pending(current_ts)
                current_terminal = new_terminal
                current_type = "buy"
                current_commodities = []
            # Sinon (même terminal re-détecté — une capture d'écran de plus
            # dans la même session de scan) : ne rien faire. Vérifié sur un
            # vrai log : "Matched terminal: X" réapparaît à chaque nouvelle
            # capture même si X n'a pas changé — le traiter comme une
            # nouvelle table à chaque fois fragmentait une longue session de
            # scan en une dizaine de petits lots séparés, dont un seul (le
            # dernier) recevait la ligne de soumission et finissait validé.
            continue

        # Type de terminal (buy/sell)
        mtype = RE_TERMINAL_TYPE.search(line)
        if mtype:
            new_type = mtype.group(1).lower()
            if new_type != current_type:
                # Changement réel de mode (achat<->vente) sur ce terminal —
                # clore le lot en cours (mode différent = table différente).
                _flush_pending(current_ts)
                current_commodities = []
                current_type = new_type
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

    # Dédupliquer les commodités dans chaque ScanResult :
    # SC-Datarunner peut logger la même commodité plusieurs fois dans un scan.
    # On garde la dernière occurrence (prix/stock les plus récents).
    for r in results:
        seen: dict[str, int] = {}  # clé → dernier index
        for i, c in enumerate(r.commodities):
            key = str(c.commodity_id) if c.commodity_id else c.name.lower()
            seen[key] = i
        r.commodities = [r.commodities[i] for i in sorted(seen.values())]

    return results, current_terminal, current_type, current_commodities
