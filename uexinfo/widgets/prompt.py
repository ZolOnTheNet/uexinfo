"""Widget PromptWidget — ligne de saisie avec complétion et historique."""
from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.suggester import Suggester
from textual.widgets import Input, Label, Static

if TYPE_CHECKING:
    from uexinfo.app import UexInfoApp

# Services de commerce prioritaires dans les suggestions
_TRADING_SVCS = {"admin", "tdd", "trade"}

# ── Arbre de commandes — navigation token par token ──────────────────────────
# Valeurs spéciales : "__arg__" = argument libre (pas de complétion de liste)
#                    "__hint__" = texte affiché dans la liste comme indication
_A = "__arg__"   # argument libre
_H = "__hint__"  # hint affiché

_CMD_TREE: dict = {
    # ── Généraux ─────────────────────────────────────────────────────────
    "help":    {},
    "h":       {},
    "exit":    {},
    "quit":    {},
    "bye":     {},

    # ── Navigation / position ─────────────────────────────────────────────
    "go": {
        "from":  {_A: "terminal d'origine"},
        "to":    {_A: "terminal de destination"},
        "clear": {},
        _A: "destination",
    },
    "lieu": {
        "from":  {_A: "terminal d'origine"},
        "to":    {_A: "terminal de destination"},
        "clear": {},
        _A: "destination",
    },
    "dest": {
        "clear":   {},
        "effacer": {},
        _A: "destination",
    },
    "arriver":  {},
    "arrivé":   {},
    "arrive":   {},
    "arrived":  {},

    # ── Sélection / filtres ───────────────────────────────────────────────
    "select": {
        "system":   {_A: "nom de système"},
        "planet":   {_A: "nom de planète"},
        "station":  {_A: "nom de station"},
        "terminal": {_A: "nom de terminal"},
        "city":     {_A: "nom de ville"},
        "outpost":  {_A: "nom d'avant-poste"},
        "add": {
            "system":   {_A: "nom"},
            "planet":   {_A: "nom"},
            "station":  {_A: "nom"},
            "terminal": {_A: "nom"},
            "city":     {_A: "nom"},
            "outpost":  {_A: "nom"},
        },
        "remove": {
            "system":   {_A: "nom"},
            "planet":   {_A: "nom"},
            "station":  {_A: "nom"},
            "terminal": {_A: "nom"},
        },
        "clear": {},
    },

    # ── Joueur ────────────────────────────────────────────────────────────
    "player": {
        "info": {},
        "ship": {
            "add":    {_A: "nom du vaisseau"},
            "set":    {_A: "nom du vaisseau"},
            "select": {_A: "nom du vaisseau"},
            "scu":    {_A: "nom du vaisseau  scu"},
            "remove": {_A: "nom du vaisseau"},
        },
        "dest": {_A: "destination"},
        _A: "@lieu",
    },

    # ── Vaisseaux ─────────────────────────────────────────────────────────
    "ship": {
        "list":   {},
        "add":    {_A: "nom du vaisseau"},
        "remove": {_A: "nom du vaisseau"},
        "set":    {_A: "nom du vaisseau"},
        "select": {_A: "nom du vaisseau"},
        "cargo":  {_A: "nom du vaisseau  scu"},
    },

    # ── Info / exploration ────────────────────────────────────────────────
    "info": {
        "terminal":  {_A: "nom de terminal"},
        "commodity": {_A: "nom de commodité"},
        "ship":      {_A: "nom de vaisseau"},
        _A: "lieu / commodité / vaisseau",
    },
    "explore": {_A: "chemin (ex: ship.crusader.cutlass_black)"},

    # ── Configuration ─────────────────────────────────────────────────────
    "config": {
        "ship": {
            "list":   {},
            "add":    {_A: "nom du vaisseau"},
            "remove": {_A: "nom du vaisseau"},
            "set":    {_A: "nom du vaisseau"},
            "select": {_A: "nom du vaisseau"},
            "cargo":  {_A: "nom du vaisseau  scu"},
        },
        "trade": {
            "profit":  {_A: "aUEC minimum par SCU"},
            "margin":  {_A: "% de marge minimum"},
            "illegal": {"on": {}, "off": {}},
        },
        "cache": {
            "ttl":   {_A: "secondes"},
            "clear": {},
        },
        "scan": {
            "mode":        {"ocr": {}, "log": {}, "confirm": {}},
            "tesseract":   {_A: "chemin vers tesseract.exe"},
            "logpath":     {_A: "chemin vers game.log"},
            "screenshots": {_A: "dossier screenshots Star Citizen"},
        },
        "player": {},
    },

    # ── Scan ──────────────────────────────────────────────────────────────
    "scan": {
        "list":       {},
        "ecran":      {},
        "screen":     {},
        "screenshot": {_A: "chemin du fichier image"},
        "log": {
            "all":   {},
            "reset": {},
            "undo":  {},
            _A: "chemin du fichier log (optionnel)",
        },
        "status":  {},
        "history": {_A: "n (optionnel, défaut 5)"},
        "debug":   {_A: "chemin du fichier image"},
        _A: "n (optionnel — scanner les n derniers screenshots)",
    },

    # ── Automatisations ───────────────────────────────────────────────────
    "auto": {
        "log":          {"on": {}, "off": {}},
        "signal.scan":  {"on": {}, "off": {}},
        "log.accept":   {"on": {}, "off": {}},
    },
    "undo": {},

    # ── Historique ────────────────────────────────────────────────────────
    "history": {
        "list":  {_A: "n (optionnel, défaut 50)"},
        "stats": {},
        "clear": {},
    },

    # ── Trading ───────────────────────────────────────────────────────────
    "trade": {
        "buy":     {_A: "commodité"},
        "sell":    {_A: "commodité"},
        "best":    {},
        "compare": {_A: "commodité"},
        "from":    {_A: "terminal d'origine"},
        "to":      {_A: "terminal de destination"},
    },

    # ── Routes / navigation ───────────────────────────────────────────────
    "route": {
        "from": {_A: "terminal de départ"},
        "to":   {_A: "terminal d'arrivée"},
    },
    "plan": {
        "new":      {},
        "add":      {_A: "terminal"},
        "remove":   {_A: "n"},
        "optimize": {},
        "clear":    {},
        "show":     {},
    },
    "nav": {
        "info":         {},
        "noeuds":       {},
        "nodes":        {},
        "liaisons":     {},
        "edges":        {},
        "sauts":        {},
        "jumps":        {},
        "route":        {_A: "départ  arrivée"},
        "add-route":    {_A: "terminal_a  terminal_b  distance"},
        "add-jump":     {_A: "système_a  système_b"},
        "remove-route": {_A: "terminal_a  terminal_b"},
        "remove-jump":  {_A: "système_a  système_b"},
        "sauvegarder":  {},
        "save":         {},
        "raz":          {},
        "populate":     {},
    },

    # ── Rafraîchissement ──────────────────────────────────────────────────
    "refresh": {
        "all":     {},
        "static":  {},
        "prices":  {},
        "sctrade": {},
        "status":  {},
    },
}


def _cmd_tree_navigate(tokens: list[str]) -> dict | None:
    """Navigue dans _CMD_TREE avec les tokens déjà validés.
    Retourne le sous-arbre courant, ou None si chemin inconnu.
    """
    node: dict = _CMD_TREE
    for tok in tokens:
        if not isinstance(node, dict) or tok not in node:
            return None
        node = node[tok]
    return node if isinstance(node, dict) else None


def _cmd_inline_suggestion(value: str) -> str | None:
    """Suggestion inline pour les saisies commençant par /.
    Retourne une chaîne commençant par `value`, ou None.
    """
    stripped = value.lstrip()
    if not stripped.startswith("/"):
        return None
    rest = stripped[1:]
    parts = rest.split(" ")

    if len(parts) == 1:
        # Complétion du nom de commande
        partial = parts[0].lower()
        for cmd in sorted(_CMD_TREE):
            if cmd.startswith(partial) and cmd != partial:
                return value + cmd[len(partial):]
        return None

    # Navigation dans l'arbre : tous les tokens sauf le dernier sont validés
    completed = [p.lower() for p in parts[:-1]]
    partial   = parts[-1].lower()

    node = _cmd_tree_navigate(completed)
    if node is None:
        return None

    for key in sorted(k for k in node if not k.startswith("__")):
        if key.startswith(partial) and key != partial:
            return value + key[len(partial):]
    return None


def _build_cmd_completions(stripped: str) -> list[tuple[str, str]]:
    """Liste de complétion pour les saisies commençant par /."""
    rest  = stripped[1:]
    parts = rest.split(" ")

    if len(parts) == 1:
        partial = parts[0].lower()
        return [
            (f"[bold]/{cmd}[/bold]", f"/{cmd} ")
            for cmd in sorted(_CMD_TREE)
            if cmd.startswith(partial)
        ]

    completed = [p.lower() for p in parts[:-1]]
    partial   = parts[-1].lower()
    # Préfixe intact (préserve la casse originale)
    prefix    = stripped[: stripped.rfind(" ") + 1]

    node = _cmd_tree_navigate(completed)
    if node is None:
        return []

    results: list[tuple[str, str]] = []
    for key in sorted(k for k in node if not k.startswith("__")):
        if key.startswith(partial):
            val = prefix + key
            # Ajouter un espace sauf si le sous-arbre est terminal (feuille vide)
            sub = node[key]
            if isinstance(sub, dict) and any(k for k in sub if not k.startswith("__")):
                val += " "
            results.append((f"[dim]{prefix}[/dim][bold]{key}[/bold]", val))

    # Hint argument libre
    if _A in node and not results:
        hint = node[_A]
        results.append((f"[dim]‹{hint}›[/dim]", prefix))

    return results


def _short(terminal_name: str) -> str:
    """'Admin - Port Tressler' → 'Port Tressler'."""
    return terminal_name.rsplit(" - ", 1)[-1].strip()


def _svc(terminal_name: str) -> str:
    """'Admin - Port Tressler' → 'admin'."""
    if " - " not in terminal_name:
        return ""
    return terminal_name.split(" - ", 1)[0].strip().lower()


def _svc_priority(svc: str) -> int:
    return 0 if svc in _TRADING_SVCS else 1


class UexSuggester(Suggester):
    """Compléteur inline :
    - `/com`          → `/config`
    - `@New B`        → `@New Babbage`  (nom court de station)
    - `New B`         → `New Babbage`   (nom court, préfère Admin/TDD)
    - `New Babbage.`  → `New Babbage.admin`
    - `New Babbage.sh`→ `New Babbage.shop`
    - `Gold`          → `Gold` (commodité)
    """

    def __init__(self, app_ref: UexInfoApp) -> None:
        super().__init__(use_cache=False, case_sensitive=False)
        self._app = app_ref

    async def get_suggestion(self, value: str) -> str | None:
        if not value:
            return None

        stripped = value.lstrip()
        ctx = getattr(self._app, "ctx", None)

        # ── Commandes / — navigation arbre ───────────────────────────────
        if stripped.startswith("/"):
            return _cmd_inline_suggestion(value)

        # ── @station (position courante) ─────────────────────────────────
        if stripped.startswith("@"):
            if ctx is None:
                return None
            partial = stripped[1:].lower().replace("_", " ")
            best = self._match_station(ctx, partial)
            if best:
                suffix = best[len(partial):]
                return value + suffix
            return None

        # ── Notation pointée  station.service ────────────────────────────
        if "." in stripped:
            return self._suggest_dotted(value, stripped, ctx)

        # ── Texte libre : d'abord station courte, puis commodité ─────────
        if ctx is None:
            return None
        norm = stripped.lower().replace("_", " ")

        # Station courte (Admin/TDD en tête)
        best = self._match_station(ctx, norm)
        if best:
            suffix = best[len(norm):]
            return value + suffix

        # Commodité
        for c in sorted(ctx.cache.commodities, key=lambda c: c.name):
            if c.name.lower().startswith(norm):
                return value + c.name[len(norm):]

        return None

    # ── Helpers ──────────────────────────────────────────────────────────

    def _match_station(self, ctx, partial: str) -> str | None:
        """Retourne le nom court de station le plus pertinent pour `partial`.
        Préfère les terminaux Admin/TDD. Retourne None si aucun match.
        """
        matches: list[tuple[int, str]] = []  # (priorité, nom_court)
        seen: set[str] = set()
        for t in ctx.cache.terminals:
            loc = _short(t.name).lower()
            if loc.startswith(partial) and loc not in seen:
                seen.add(loc)
                matches.append((_svc_priority(_svc(t.name)), _short(t.name)))
        if not matches:
            return None
        matches.sort(key=lambda x: (x[0], x[1]))
        return matches[0][1]  # nom court avec casse d'origine

    def _suggest_dotted(self, value: str, stripped: str, ctx) -> str | None:
        """Complète  `Station.svc_prefix`  →  `Station.service`."""
        if ctx is None:
            return None

        dot_pos = stripped.rfind(".")
        station_raw = stripped[:dot_pos]
        svc_prefix   = stripped[dot_pos + 1:].lower()

        # Normaliser la station (ignorer préfixe système éventuel)
        station_q = station_raw.rsplit(".", 1)[-1].lower().replace("_", " ").strip()

        # Trouver tous les services disponibles à cette station
        services: list[tuple[int, str]] = []  # (priorité, svc)
        for t in ctx.cache.terminals:
            if " - " not in t.name:
                continue
            loc = _short(t.name).lower()
            svc = _svc(t.name)
            if loc == station_q and svc.startswith(svc_prefix):
                services.append((_svc_priority(svc), svc))

        if not services:
            return None

        services.sort()
        best_svc = services[0][1]
        suffix = best_svc[len(svc_prefix):]
        return value + suffix


def _build_completions(query: str, ctx) -> list[tuple[str, str]]:
    """Construit la liste de complétion pour la liste déroulante (Ctrl+↓).

    Ordre :
      0. Commandes / — navigation arbre
      1. Préfixe sur nom court de station  (Admin/TDD en tête)
      2. Contenu  sur nom court de station
      3. Préfixe  sur commodité
      4. Contenu  sur commodité
    Notation pointée (station.svc_prefix) → liste les services.
    """
    if not query:
        return []

    q = query.lower()

    # ── Commandes / ───────────────────────────────────────────────────────
    if q.startswith("/"):
        return _build_cmd_completions(query.lstrip())

    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    # ── Notation pointée : station.service ──────────────────────────────
    if "." in q:
        dot = q.rfind(".")
        station_q = q[:dot].rsplit(".", 1)[-1].strip()
        svc_prefix = q[dot + 1:]
        svcs: list[tuple[int, str, str]] = []  # (priority, svc, station_display)
        for t in ctx.cache.terminals:
            if " - " not in t.name:
                continue
            svc = _svc(t.name)
            loc = _short(t.name)
            if loc.lower() == station_q and svc.startswith(svc_prefix):
                prio = 0 if svc in _TRADING_SVCS else 1
                key = f"{loc}.{svc}"
                if key not in seen:
                    seen.add(key)
                    svcs.append((prio, svc, loc))
        svcs.sort()
        for _, svc, loc in svcs:
            # Garder le préfixe système si présent dans la saisie originale
            prefix = q[:q.rfind(loc.lower())]
            val = f"{prefix}{loc}.{svc}"
            results.append((f"[cyan]{loc}[/cyan].[dim]{svc}[/dim]", val))
        return results

    # ── Stations : préfixe ───────────────────────────────────────────────
    stations_prefix: list[tuple[int, str]] = []
    for t in ctx.cache.terminals:
        loc = _short(t.name)
        if loc.lower().startswith(q) and loc not in seen:
            seen.add(loc)
            prio = 0 if _svc(t.name) in _TRADING_SVCS else 1
            stations_prefix.append((prio, loc))
    stations_prefix.sort()
    for _, loc in stations_prefix:
        results.append((f"[cyan]{loc}[/cyan]", loc))

    # ── Stations : contient ──────────────────────────────────────────────
    stations_cont: list[tuple[str]] = []
    for t in ctx.cache.terminals:
        loc = _short(t.name)
        if q in loc.lower() and not loc.lower().startswith(q) and loc not in seen:
            seen.add(loc)
            stations_cont.append((loc,))
    stations_cont.sort()
    for (loc,) in stations_cont:
        results.append((f"[dim]{loc}[/dim]", loc))

    # ── Commodités : préfixe ─────────────────────────────────────────────
    for c in sorted(ctx.cache.commodities, key=lambda c: c.name):
        if c.name.lower().startswith(q) and c.name not in seen:
            seen.add(c.name)
            results.append((f"[yellow]{c.name}[/yellow]", c.name))

    # ── Commodités : contient ────────────────────────────────────────────
    for c in sorted(ctx.cache.commodities, key=lambda c: c.name):
        if q in c.name.lower() and not c.name.lower().startswith(q) and c.name not in seen:
            seen.add(c.name)
            results.append((f"[dim]{c.name}[/dim]", c.name))

    return results[:30]


_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class PromptWidget(Static):
    """Ligne de saisie dockée en bas avec historique (↑↓) et complétion inline."""

    BINDINGS = [
        Binding("up",        "history_prev",      "Précédent", show=False),
        Binding("down",      "history_next",      "Suivant",   show=False),
        Binding("ctrl+down", "show_completions",  "Compléter", show=False),
        Binding("tab",       "accept_tab",        "Compléter", show=False),
    ]

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def __init__(self) -> None:
        super().__init__()
        self._history: list[str] = []
        self._hist_idx: int = -1
        self._pending: str = ""
        self._spinner_idx: int = 0
        self._spinner_timer = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="prompt-row"):
            yield Label("[cyan bold]›[/cyan bold] ", id="prompt-symbol", markup=True)
            yield Input(
                placeholder="commande ou nom de lieu/commodité…",
                id="prompt-input",
                suggester=None,          # sera injecté après mount
            )

    def on_mount(self) -> None:
        inp = self.query_one("#prompt-input", Input)
        app: UexInfoApp = self.app  # type: ignore[assignment]
        inp.suggester = UexSuggester(app)

    # ── Spinner ───────────────────────────────────────────────────────────

    def start_spinner(self) -> None:
        """Démarre l'animation du spinner (appelé depuis le thread worker)."""
        self._spinner_idx = 0
        if self._spinner_timer is None:
            self._spinner_timer = self.set_interval(0.1, self._tick_spinner)

    def stop_spinner(self) -> None:
        """Arrête le spinner et restaure le symbole ›."""
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self.query_one("#prompt-symbol", Label).update("[cyan bold]›[/cyan bold] ")

    def _tick_spinner(self) -> None:
        self._spinner_idx = (self._spinner_idx + 1) % len(_SPINNER_FRAMES)
        ch = _SPINNER_FRAMES[self._spinner_idx]
        self.query_one("#prompt-symbol", Label).update(f"[cyan]{ch}[/cyan] ")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if value:
            # Ajouter à l'historique (sans doublon consécutif)
            if not self._history or self._history[-1] != value:
                self._history.append(value)
        self._hist_idx = -1
        self._pending = ""
        event.input.clear()
        self.post_message(self.Submitted(value))

    def action_history_prev(self) -> None:
        if not self._history:
            return
        inp = self.query_one("#prompt-input", Input)
        if self._hist_idx == -1:
            self._pending = inp.value
            self._hist_idx = len(self._history) - 1
        elif self._hist_idx > 0:
            self._hist_idx -= 1
        inp.value = self._history[self._hist_idx]
        inp.cursor_position = len(inp.value)

    def action_history_next(self) -> None:
        if self._hist_idx == -1:
            return
        inp = self.query_one("#prompt-input", Input)
        if self._hist_idx < len(self._history) - 1:
            self._hist_idx += 1
            inp.value = self._history[self._hist_idx]
        else:
            self._hist_idx = -1
            inp.value = self._pending
        inp.cursor_position = len(inp.value)

    def action_accept_tab(self) -> None:
        """Tab — accepte la suggestion inline si présente, sinon ouvre la liste."""
        inp = self.query_one("#prompt-input", Input)
        suggestion = getattr(inp, "_suggestion", None)
        if suggestion and suggestion != inp.value:
            inp.value = suggestion
            inp.cursor_position = len(suggestion)
        else:
            self.action_show_completions()

    def action_show_completions(self) -> None:
        """Ctrl+↓ — ouvre la liste déroulante de complétion."""
        from uexinfo.widgets.completion_list import CompletionList
        inp = self.query_one("#prompt-input", Input)
        query = inp.value.strip().replace("_", " ")
        ctx = getattr(self.app, "ctx", None)
        if ctx is None:
            return
        items = _build_completions(query, ctx)
        try:
            cl = self.app.query_one(CompletionList)
            cl.show_items(items)
        except Exception:
            pass

    def accept_completion(self, value: str) -> None:
        """Appelé par CompletionList.Accepted — remplit l'input."""
        inp = self.query_one("#prompt-input", Input)
        inp.value = value
        inp.cursor_position = len(value)
        inp.focus()
