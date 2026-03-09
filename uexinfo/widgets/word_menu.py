"""WordMenu — menu contextuel flottant pour les mots cliqués dans le RichLog."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label


class WordMenu(Widget):
    """Menu contextuel à 2 options affiché sur clic-droit dans le RichLog."""

    class Action(Message):
        """Émis quand l'utilisateur choisit une action."""

        def __init__(self, action: str, word: str) -> None:
            super().__init__()
            self.action = action
            self.word = word

    DEFAULT_CSS = """
    WordMenu {
        layer: overlay;
        background: $panel;
        border: solid $accent;
        width: 28;
        height: auto;
        padding: 0;
    }
    WordMenu > Label {
        height: 1;
        width: 1fr;
        padding: 0 1;
    }
    WordMenu > Label:hover {
        background: $accent;
        color: $text;
    }
    WordMenu > Label#wm-title {
        background: $panel-darken-2;
        text-style: bold;
        color: $accent;
    }
    """

    def __init__(self, word: str, x: int, y: int) -> None:
        super().__init__()
        self._word = word
        # positionner le menu à l'écran
        self.styles.offset = (x, y)

    def compose(self) -> ComposeResult:
        truncated = self._word[:20] + "…" if len(self._word) > 21 else self._word
        yield Label(truncated, id="wm-title")
        yield Label("ℹ  /info", id="wm-info")
        yield Label("🧭  /go  (aller à)", id="wm-go")
        yield Label("📍  /dest  (destination)", id="wm-dest")
        yield Label("🚀  Activer  (/ship set)", id="wm-ship")
        yield Label("✕  Fermer", id="wm-close")

    def on_click(self, event) -> None:
        event.stop()
        wid = getattr(event.widget, "id", None)
        if wid == "wm-info":
            self.post_message(self.Action("info", self._word))
        elif wid == "wm-go":
            self.post_message(self.Action("go", self._word))
        elif wid == "wm-dest":
            self.post_message(self.Action("dest", self._word))
        elif wid == "wm-ship":
            self.post_message(self.Action("ship_set", self._word))
        self.remove()
