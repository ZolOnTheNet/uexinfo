"""CompletionList — liste déroulante de complétion (Ctrl+↓)."""
from __future__ import annotations

from textual.message import Message
from textual.widgets import ListItem, ListView, Label


class CompletionList(ListView):
    """Liste déroulante cachée par défaut.

    Affichée via Ctrl+↓ depuis le PromptWidget.
    Fermeture : Échap ou sélection d'un item.
    """

    class Accepted(Message):
        """Envoyé quand l'utilisateur valide un item."""
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def show_items(self, items: list[tuple[str, str]]) -> None:
        """Affiche la liste avec items = [(texte_affiché, valeur), ...]."""
        self.clear()
        if not items:
            self.display = False
            return
        for display, value in items[:15]:
            item = ListItem(Label(display, markup=True))
            item._completion_value = value  # type: ignore[attr-defined]
            self.append(item)
        self.display = True
        self.focus()
        self.index = 0

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        value = getattr(event.item, "_completion_value", None)
        if value is None:
            # Fallback : texte brut du Label
            lbl = event.item.query_one(Label)
            value = str(lbl.renderable)
        self.display = False
        self.post_message(self.Accepted(value))
        event.stop()

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.display = False
            event.prevent_default()
            event.stop()
