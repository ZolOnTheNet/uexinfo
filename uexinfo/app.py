"""App Textual — interface terminal interactive uexinfo."""
from __future__ import annotations

# ── ÉTAPE 1 : remplacer le console Rich par un console qui écrit dans un
#    StringIO avec force_terminal=True → les codes ANSI sont émis normalement.
#    Doit se faire AVANT d'importer les modules de commandes (qui font
#    `from uexinfo.display.formatter import console`).
import io as _io
import re as _re
import uexinfo.display.formatter as _fmt_mod
from rich.console import Console as _Console

_output_buf: _io.StringIO = _io.StringIO()

_fmt_mod.console = _Console(
    file=_output_buf,
    force_terminal=True,
    markup=True,
    highlight=True,
    width=120,          # sera ajusté dynamiquement sur resize
)

# ── ÉTAPE 2 : imports normaux (utilisent le nouveau console) ──────────────────
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Input, Static

import uexinfo.config.settings as settings
import uexinfo.cli.history as _history_mod
from uexinfo import __version__
from uexinfo.cache.manager import CacheManager
from uexinfo.cli.main import AppContext
from uexinfo.cli.runner import run_command
from uexinfo.location.index import LocationIndex
from uexinfo.models.player import Player
from uexinfo.widgets.output import OutputView
from uexinfo.widgets.status_bar import StatusBar
from uexinfo.widgets.completion_list import CompletionList
from uexinfo.widgets.prompt import PromptWidget
from uexinfo.widgets.word_menu import WordMenu

# Capture 1 à 4 mots séparés par UN espace (noms composés : "Terra Gateway",
# "New Babbage", "Port Tressler"…). S'arrête aux doubles-espaces, │, (, ), chiffres.
_RE_CLICK_WORD = _re.compile(
    r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9'\-]*"
    r"(?:[ ][A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9'\-]*){0,3}"
)

# Enregistrement des commandes CLI (imports déclenchent @register)
import uexinfo.cli.commands.help     # noqa: F401
import uexinfo.cli.commands.config   # noqa: F401
import uexinfo.cli.commands.refresh  # noqa: F401
import uexinfo.cli.commands.go       # noqa: F401
import uexinfo.cli.commands.select   # noqa: F401
import uexinfo.cli.commands.player   # noqa: F401
import uexinfo.cli.commands.scan     # noqa: F401
import uexinfo.cli.commands.info     # noqa: F401
import uexinfo.cli.commands.explore  # noqa: F401
import uexinfo.cli.commands.trade    # noqa: F401
import uexinfo.cli.commands.nav          # noqa: F401
import uexinfo.cli.commands.history_cmd  # noqa: F401
import uexinfo.cli.commands.debug        # noqa: F401
import uexinfo.cli.commands.auto         # noqa: F401
import uexinfo.cli.commands.undo         # noqa: F401


class UexInfoApp(App):
    """UEXInfo — interface terminal interactive Star Citizen."""

    CSS_PATH = "styles/app.tcss"
    TITLE = f"uexinfo v{__version__}"

    BINDINGS = [
        Binding("ctrl+c",  "quit",              "Quitter",  show=False),
        Binding("ctrl+l",  "clear_output",      "Effacer"),
        Binding("ctrl+y",  "copy_to_clipboard", "Copier"),
        Binding("f1",      "show_help",         "Aide"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.ctx: AppContext | None = None

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield OutputView(id="output")
        yield CompletionList(id="completion-list")
        yield PromptWidget()
        yield StatusBar(id="status-bar")
        yield Footer()

    # ── Démarrage ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._init_context()

    def on_resize(self, event) -> None:
        _fmt_mod.console._width = max(40, event.size.width - 2)

    def _init_context(self) -> None:
        out = self.query_one(OutputView)
        _fmt_mod.console._width = max(40, self.size.width - 2)

        cfg = settings.load()
        ttl = cfg.get("cache", {}).get("ttl_static", 86400)
        cache = CacheManager(ttl_static=ttl)

        try:
            cache.load()
        except Exception as e:
            out.write_markup(f"[yellow]⚠  Cache indisponible : {e}[/yellow]")

        self.ctx = AppContext(cfg=cfg, cache=cache)
        self.ctx.location_index = LocationIndex(cache)
        self.ctx.player = Player.from_config(cfg.get("player", {}))

        # Migration ancienne config ships/cargo → player
        if not self.ctx.player.ships:
            _old_avail = cfg.get("ships", {}).get("available", [])
            if _old_avail:
                from uexinfo.models.player import Ship as _Ship
                _old_cargo = cfg.get("cargo", {})
                _old_cur   = cfg.get("ships", {}).get("current", "")
                self.ctx.player.ships = [
                    _Ship(name=n, scu=_old_cargo.get(n, 0) or 0)
                    for n in _old_avail
                ]
                if _old_cur and not self.ctx.player.active_ship:
                    self.ctx.player.active_ship = _old_cur
                cfg["player"] = self.ctx.player.to_config()
                settings.save(cfg)

        # Bannière
        out.write_markup(
            f"[bold cyan]UEXInfo[/bold cyan] [dim]v{__version__}[/dim]"
            "  —  Star Citizen Trade CLI"
        )
        out.write_markup(
            "[dim]  /help · saisie libre = /info · @lieu = se positionner + info[/dim]"
        )
        out.write_markup(
            "[dim]  Complétion : [bold]→[/bold] ou [bold]Tab[/bold] (inline)"
            " · [bold]Ctrl+↓[/bold] (liste)"
            " · [bold]↑↓[/bold] = historique[/dim]"
        )
        out.write_markup(
            "[dim]  Copier : [bold]Ctrl+Y[/bold] = tout copier dans le presse-papiers"
            " · [bold]Shift+clic-glisser[/bold] = sélection native dans le terminal[/dim]"
        )
        out.write_markup(
            "[dim]  Clic [bold]gauche[/bold] sur un mot = /info"
            " · Clic [bold]droit[/bold] = menu contextuel[/dim]"
        )

        # Mettre à jour la StatusBar
        self.query_one(StatusBar).refresh_status(self.ctx)

        # Charger l'historique persistant dans le PromptWidget
        prompt = self.query_one(PromptWidget)
        prompt._history = _history_mod.last_n(500)

        # Focaliser le prompt
        self.query_one("#prompt-input").focus()

    # ── Réception de la saisie ────────────────────────────────────────────────

    def on_prompt_widget_submitted(self, event: PromptWidget.Submitted) -> None:
        line = event.value.strip()
        if not line:
            return
        if line.lower() in ("exit", "quit", "bye", "/exit", "/quit", "/bye"):
            self._do_exit()
            return
        _history_mod.append(line)
        self._run_command(line)

    def on_completion_list_accepted(self, event: CompletionList.Accepted) -> None:
        """Quand un item de la liste déroulante est sélectionné."""
        self.query_one(PromptWidget).accept_completion(event.value)

    def on_click(self, event) -> None:
        """Clic sur l'OutputView → mot interactif ; ailleurs → focus input."""
        target = event.widget

        if isinstance(target, (OutputView, Static)):
            # Fermer tout menu ouvert
            for m in self.query(WordMenu):
                m.remove()

            word = self._word_at_click(event)

            if event.button == 3 and word:
                self._show_word_menu(word, event.screen_x, event.screen_y)
                return
            if event.button == 1 and word:
                self._run_command(f"/info {word}")
            self.query_one("#prompt-input").focus()
            return

        if isinstance(target, (Input, CompletionList)):
            return

        # Clic sur tout autre widget → fermer menus + focus input
        for m in self.query(WordMenu):
            m.remove()
        self.query_one("#prompt-input").focus()

    def _word_at_click(self, event) -> str:
        """Extrait le mot textuel sous le curseur depuis le line_index de l'OutputView."""
        out = self.query_one(OutputView)
        col = max(0, event.x - 1)
        line_idx = int(out.scroll_y) + event.y

        for delta in (0, 1, -1, 2, -2):
            idx = line_idx + delta
            lines = out.line_index
            if not (0 <= idx < len(lines)):
                continue
            line = lines[idx]
            for m in _RE_CLICK_WORD.finditer(line):
                if m.start() <= col <= m.end():
                    word = m.group()
                    if len(word) >= 3 and not word.isdigit():
                        return word
        return ""

    def _show_word_menu(self, word: str, x: int, y: int) -> None:
        """Affiche le menu contextuel flottant au point (x, y) écran."""
        menu = WordMenu(word, x, y)
        self.screen.mount(menu)

    def on_word_menu_action(self, event: WordMenu.Action) -> None:
        """Réaction aux actions du menu contextuel."""
        if event.action == "info":
            self._run_command(f"/info {event.word}")
        elif event.action == "go":
            self._run_command(f"/go {event.word}")
        elif event.action == "dest":
            self._run_command(f"/dest {event.word}")
        elif event.action == "ship_set":
            self._run_command(f"/ship set {event.word}")
        self.query_one("#prompt-input").focus()

    # ── Exécution des commandes ───────────────────────────────────────────────

    @work(thread=True, exclusive=True)
    def _run_command(self, line: str) -> None:
        """Exécuter une commande dans un thread, capturer la sortie Rich → OutputView."""
        if self.ctx is None:
            return

        out = self.query_one(OutputView)
        prompt = self.query_one(PromptWidget)
        _fmt_mod.console._width = max(40, self.size.width - 2)

        # Vider le buffer StringIO avant d'exécuter
        _output_buf.truncate(0)
        _output_buf.seek(0)

        # Echo de la saisie
        self.call_from_thread(
            out.write_rich,
            Text.from_markup(f"[dim cyan]›[/dim cyan] [bold]{line}[/bold]"),
        )

        # Démarrer le spinner
        self.call_from_thread(prompt.start_spinner)

        _needs_bar_sync = False

        try:
            from uexinfo.cli.commands.scan import (
                check_log_auto, check_screenshots_auto, _display_scan,
            )
            from uexinfo.cli.main import AppContext as _AC

            first_word = line.strip().lstrip("/").split()[0].lower() if line.strip() else ""
            _is_info = first_word == "info" or (
                not line.strip().startswith("/") and not line.strip().startswith("@")
                and first_word not in ("scan", "s")
            )

            # Pre-hook : avant /info, mise à jour silencieuse du ctx
            if _is_info:
                check_log_auto(self.ctx)

            dispatched = run_command(line, self.ctx)
            _needs_bar_sync = bool(dispatched & {"player", "go", "lieu", "ship", "config"})

            # Post-hook : après les autres commandes, afficher nouveaux scans + screenshots
            if not _is_info and first_word not in ("scan", "s"):
                _new = check_log_auto(self.ctx)
                for _r in _new:
                    _display_scan(_r, self.ctx)
                _new_shots = check_screenshots_auto(self.ctx)
                if _new_shots:
                    from uexinfo.display.formatter import console
                    from uexinfo.display import colors as C
                    console.print(
                        f"\n[{C.DIM}]── {len(_new_shots)} nouveau(x) screenshot(s) SC ──[/{C.DIM}]"
                    )
                    for _p in _new_shots:
                        console.print(
                            f"  [{C.LABEL}]{_p.name}[/{C.LABEL}]"
                            f"  [{C.DIM}]→ scan screenshot {_p.name}[/{C.DIM}]"
                        )
        except Exception as e:
            self.call_from_thread(prompt.stop_spinner)
            self._flush_output(out)
            self.call_from_thread(
                out.write_markup,
                f"[red]✗ Erreur : {e}[/red]",
            )
            return

        self.call_from_thread(prompt.stop_spinner)

        if _needs_bar_sync:
            self.call_from_thread(
                self.query_one(StatusBar).refresh_status, self.ctx
            )

        self._flush_output(out)

    def _flush_output(self, out: OutputView) -> None:
        """Récupérer la sortie du buffer StringIO et l'injecter dans l'OutputView."""
        output = _output_buf.getvalue()
        _output_buf.truncate(0)
        _output_buf.seek(0)

        if not output.strip():
            return

        # Nettoyer les \r résiduels (Windows)
        output = output.replace("\r\n", "\n").replace("\r", "\n").rstrip()
        self.call_from_thread(out.write_ansi, output)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_clear_output(self) -> None:
        self.query_one(OutputView).clear()

    def action_copy_to_clipboard(self) -> None:
        """Ctrl+Y — copie tout le contenu affiché dans le presse-papiers."""
        import subprocess
        out = self.query_one(OutputView)
        text = out.plain_text
        if not text:
            return
        try:
            subprocess.run(
                "clip",
                input=text.encode("utf-8", errors="replace"),
                check=False,
                shell=True,
            )
            out.write_markup("[dim green]✓  Copié dans le presse-papiers[/dim green]")
        except Exception:
            pass

    def on_status_bar_command_request(self, event: StatusBar.CommandRequest) -> None:
        """Commandes déclenchées par les boutons de la StatusBar."""
        self._run_command(event.command)

    def action_show_help(self) -> None:
        self._run_command("/help")

    def _do_exit(self) -> None:
        if self.ctx and self.ctx.cache.transport_graph.has_unsaved_changes:
            try:
                self.ctx.cache.save_transport_graph()
                self.query_one(OutputView).write_markup("[green]✓  Graphe sauvegardé[/green]")
            except Exception:
                pass
        self.exit()


def main() -> None:
    UexInfoApp().run()


if __name__ == "__main__":
    main()
