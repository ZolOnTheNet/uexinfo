"""Autocomplétion contextuelle via prompt_toolkit."""
from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

if TYPE_CHECKING:
    from uexinfo.cli.main import AppContext

# Sous-commandes statiques connues
_SUBS: dict[str, list[str]] = {
    "help":          [],
    "config":        ["ship", "trade", "cache"],
    "config ship":   ["add", "remove", "set", "cargo"],
    "config trade":  ["profit", "margin", "illegal"],
    "config cache":  ["ttl", "clear"],
    "go":            ["from", "to", "clear"],
    "lieu":          ["from", "to", "clear"],
    "select":        ["system", "planet", "station", "terminal", "city", "outpost",
                      "add", "remove", "clear"],
    "select add":    ["system", "planet", "station", "terminal", "city", "outpost"],
    "select remove": ["system", "planet", "station", "terminal", "city", "outpost"],
    "trade":         ["buy", "sell", "best", "compare"],
    "trade best":    ["--profit", "--roi", "--margin", "--scu"],
    "route":         ["from", "to", "--commodity", "--min-profit", "--scu"],
    "plan":          ["new", "add", "remove", "optimize", "clear", "show"],
    "info":          ["terminal", "commodity", "ship"],
    "refresh":       ["all", "static", "prices", "sctrade", "status"],
    "exit":          [],
    "quit":          [],
}

_ALL_COMMANDS = sorted({k.split()[0] for k in _SUBS})

# Commandes qui complètent avec des noms de commodités
_COMMODITY_CMDS = {"trade", "info"}
# Commandes qui complètent avec des noms de terminaux
_TERMINAL_CMDS = {"go", "lieu", "route", "info"}


class UEXCompleter(Completer):
    def __init__(self, ctx: "AppContext | None" = None):
        self.ctx = ctx

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor.lstrip()

        if not text.startswith("/"):
            return

        after = text[1:]
        words = after.split()
        ends_space = text.endswith(" ")

        # ── Complétion du nom de commande ────────────────────────────────
        if not words or (len(words) == 1 and not ends_space):
            prefix = words[0].lower() if words else ""
            for cmd in _ALL_COMMANDS:
                if cmd.startswith(prefix):
                    yield Completion(cmd, start_position=-len(prefix))
            return

        cmd = words[0].lower()

        # ── Complétion des sous-commandes ────────────────────────────────
        if ends_space:
            typed_args = words[1:]
            current = ""
        else:
            typed_args = words[1:-1]
            current = words[-1] if len(words) > 1 else ""

        # Construire la clé de contexte
        context_key = cmd
        if typed_args:
            context_key = f"{cmd} {typed_args[0].lower()}"

        candidates = _SUBS.get(context_key, [])
        if not candidates and not typed_args:
            candidates = _SUBS.get(cmd, [])

        cur_lower = current.lower()
        for c in candidates:
            if c.startswith(cur_lower):
                yield Completion(c, start_position=-len(current))

        # ── Complétion dynamique : commodités ────────────────────────────
        if self.ctx and cmd in _COMMODITY_CMDS and (ends_space or len(words) >= 2):
            for c in self.ctx.cache.commodities:
                name = c.name
                if name.lower().startswith(cur_lower):
                    yield Completion(
                        name,
                        start_position=-len(current),
                        display=f"{name}  ({c.code})",
                        display_meta=c.kind,
                    )

        # ── Complétion dynamique : terminaux ─────────────────────────────
        if self.ctx and cmd in _TERMINAL_CMDS and (ends_space or len(words) >= 2):
            for t in self.ctx.cache.terminals:
                name = t.name
                if name.lower().startswith(cur_lower):
                    yield Completion(
                        name,
                        start_position=-len(current),
                        display=name,
                        display_meta=t.location,
                    )

        # ── Complétion dynamique : vaisseaux ─────────────────────────────
        if self.ctx and cmd == "config" and typed_args and typed_args[0] == "ship":
            ships = self.ctx.cfg.get("ships", {}).get("available", [])
            for s in ships:
                if s.lower().startswith(cur_lower):
                    yield Completion(s, start_position=-len(current))
