"""CapturingConsole — remplacement drop-in de Rich Console.

Capture les renderables Rich (Text, Table, …) avant la conversion ANSI,
tout en maintenant un buffer ANSI interne (accès via flush_ansi()).

Avantage : le renderer HTML Python génère des spans cohérents — pas de
fragmentation ANSI → les termes du vocabulaire restent dans un seul nœud DOM.
"""
from __future__ import annotations

import io
from typing import Any

from rich.console import Console


class CapturingConsole(Console):
    """Drop-in replacement for Rich Console.

    - highlight=False par défaut : empêche le ReprHighlighter de fragmenter
      des mots comme "Area 18" en deux spans distincts.
    - Les renderables sont stockés dans _renderables pour le rendu HTML natif.
    - Le buffer ANSI interne (_ansi_buf) reste disponible comme fallback.
    """

    def __init__(self, width: int = 100, **kwargs) -> None:
        self._ansi_buf = io.StringIO()
        kwargs.setdefault("force_terminal", True)
        kwargs.setdefault("markup", True)
        kwargs.setdefault("highlight", False)
        super().__init__(file=self._ansi_buf, width=width, **kwargs)
        self._renderables: list[Any] = []

    # ── Interception ──────────────────────────────────────────────────────────

    def print(self, *objects: Any, **kwargs) -> None:
        if not objects:
            self._renderables.append(None)   # ligne vide
        else:
            for obj in objects:
                self._renderables.append(obj)
        super().print(*objects, **kwargs)

    # ── Gestion des buffers ───────────────────────────────────────────────────

    def reset_capture(self) -> None:
        """Vide les renderables ET le buffer ANSI (à appeler avant chaque commande)."""
        self._renderables.clear()
        self._ansi_buf.truncate(0)
        self._ansi_buf.seek(0)

    def flush_ansi(self) -> str:
        """Retourne le buffer ANSI et le vide."""
        val = self._ansi_buf.getvalue()
        self._ansi_buf.truncate(0)
        self._ansi_buf.seek(0)
        return val

    def peek_ansi(self) -> str:
        """Lit le buffer ANSI sans le vider (pour le streaming de progression)."""
        return self._ansi_buf.getvalue()

    def flush_renderables(self) -> list[Any]:
        """Retourne et vide la liste des renderables capturés."""
        result = list(self._renderables)
        self._renderables.clear()
        return result
