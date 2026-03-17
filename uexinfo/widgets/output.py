"""OutputView — zone de sortie enrichie (Phase A).

Remplace RichLog. Fondations pour Phase B (mots cliquables).

- Reçoit du texte Rich (ANSI) via write_rich / write_markup / write_ansi
- Conserve un buffer texte brut pour la copie (sans markup)
- Auto-scroll bas après chaque bloc
- clear() réinitialise les deux buffers
"""
from __future__ import annotations

import re

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

# Retire les codes ANSI pour le presse-papiers
_RE_ANSI = re.compile(r"\x1b\[[0-9;]*[mK]")


class OutputView(VerticalScroll):
    """Zone de sortie scrollable, copiable, prête pour les mots cliquables."""

    DEFAULT_CSS = """
    OutputView {
        height: 1fr;
        padding: 0 1;
        background: $surface;
        scrollbar-gutter: stable;
    }
    OutputView Static {
        width: 1fr;
        height: auto;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._plain_blocks: list[str] = []   # blocs texte brut pour Ctrl+Y
        self._line_index:   list[str] = []   # lignes brutes pour clic-mots (Phase B)

    # ── API publique ──────────────────────────────────────────────────────────

    def write_rich(self, text: Text) -> None:
        """Ajouter un objet Rich Text dans la zone de sortie."""
        plain = text.plain
        if plain.strip():
            self._plain_blocks.append(plain.strip())
            self._line_index.extend(plain.splitlines())
        self.mount(Static(text, markup=False))
        self.call_after_refresh(lambda: self.scroll_end(animate=False))

    def write_markup(self, markup: str) -> None:
        """Ajouter une ligne Rich markup (ex: bannière)."""
        self.write_rich(Text.from_markup(markup))

    def write_ansi(self, ansi_output: str) -> None:
        """Ajouter une sortie ANSI brute (depuis le buffer StringIO console Rich)."""
        if not ansi_output.strip():
            return

        # Texte brut pour buffers internes
        plain_raw = _RE_ANSI.sub("", ansi_output)
        leading_blanks = len(plain_raw) - len(plain_raw.lstrip("\n"))
        plain = plain_raw.strip()
        if plain:
            self._plain_blocks.append(plain)
            self._line_index.extend([""] * leading_blanks)
            self._line_index.extend(plain.splitlines())

        # Rendu Rich pour l'affichage
        try:
            rich_text = Text.from_ansi(ansi_output)
        except Exception:
            rich_text = Text(plain)

        self.mount(Static(rich_text, markup=False))
        self.call_after_refresh(lambda: self.scroll_end(animate=False))

    def clear(self) -> None:
        """Effacer tout le contenu affiché et les buffers."""
        self._plain_blocks.clear()
        self._line_index.clear()
        for child in list(self.children):
            child.remove()

    # ── Accès aux buffers ──────────────────────────────────────────────────────

    @property
    def plain_text(self) -> str:
        """Tout le contenu en texte brut (pour Ctrl+Y)."""
        return "\n\n".join(self._plain_blocks)

    @property
    def line_index(self) -> list[str]:
        """Liste de toutes les lignes (pour clic-mots, Phase B)."""
        return self._line_index
