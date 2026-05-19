"""Commande /note — notes personnelles par lieu.

Syntaxe :
  /note                         Lister toutes les notes
  /note -l <lieu>               Lister les notes d'un lieu
  /note <message>               Ajouter au lieu courant
  /note -l <lieu> <message>     Ajouter à un lieu précis
  /note -e                      Formulaire de création au lieu courant
  /note -e -n <id>              Formulaire d'édition de la note <id>
  /note -r <id|lieu>            Supprimer note(s) par ID ou par lieu

Les options précèdent toujours le message.
"""
from __future__ import annotations

from datetime import datetime

from uexinfo.cli.commands import register
from uexinfo.display.formatter import console, print_ok, print_error, print_warn, section
from uexinfo.display import colors as C


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y")


def _normalize_loc(name: str) -> str:
    from uexinfo.cache.data_manager import _loc_short
    return _loc_short(name.replace("_", " ").strip()).strip()


def _current_loc(ctx) -> str:
    loc = (ctx.player.location or "").strip()
    return _normalize_loc(loc) if loc else ""


# ── Parsing des options ───────────────────────────────────────────────────────

def _parse_args(args: list[str]) -> dict | None:
    """Options obligatoirement en début de ligne, avant le message."""
    result: dict = {"edit": False, "rm": None, "note_id": None,
                    "location": None, "message": None}
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-e", "--edit"):
            result["edit"] = True
        elif a in ("-r", "--rm"):
            i += 1
            if i < len(args):
                result["rm"] = args[i]
            else:
                print_error("Option -r attend un numéro ou un lieu.")
                return None
        elif a in ("-n", "--num"):
            i += 1
            if i < len(args):
                try:
                    result["note_id"] = int(args[i])
                except ValueError:
                    print_error(f"Numéro de note invalide : {args[i]}")
                    return None
            else:
                print_error("Option -n attend un numéro.")
                return None
        elif a in ("-l", "--lieu"):
            i += 1
            if i < len(args):
                result["location"] = args[i].replace("_", " ").strip()
            else:
                print_error("Option -l attend un lieu.")
                return None
        elif a.startswith("-"):
            print_error(f"Option inconnue : {a}  — tapez /note help")
            return None
        else:
            result["message"] = " ".join(args[i:])
            break
        i += 1
    return result


# ── Affichage ─────────────────────────────────────────────────────────────────

def _display_notes(notes: list[dict], title: str, ctx=None) -> None:
    """Affiche une liste de notes ; envoie note_list à l'overlay si actif."""
    pending = getattr(ctx, "_overlay_msgs", None)

    if not notes:
        print_warn("Aucune note.")
        return

    # Overlay : HTML avec boutons [−], pas de console.print (évite le double affichage)
    if pending is not None:
        pending.append({
            "type":  "note_list",
            "notes": [
                {"id": n["id"], "location": n["location"],
                 "message": n["message"], "date": _fmt_ts(n.get("timestamp", 0))}
                for n in notes
            ],
        })
        return

    # CLI : affichage texte
    section(title)
    for n in notes:
        console.print(
            f"  [{C.DIM}]#{n['id']:3d}[/{C.DIM}]"
            f"  [{C.LABEL}]{n['location']}[/{C.LABEL}]"
            f"  [{C.DIM}]{_fmt_ts(n.get('timestamp', 0))}[/{C.DIM}]  {n['message']}"
        )


# ── Éditeur TUI ───────────────────────────────────────────────────────────────

def _open_editor(initial_loc: str, initial_msg: str,
                 note_id: int | None = None) -> tuple[str, str] | None:
    """Ouvre un formulaire plein-écran via prompt_toolkit.

    Retourne (loc, message) ou None si annulé.
    """
    try:
        from prompt_toolkit import Application
        from prompt_toolkit.buffer import Buffer
        from prompt_toolkit.document import Document
        from prompt_toolkit.layout import Layout, HSplit, Window, BufferControl
        from prompt_toolkit.widgets import TextArea, Label, Box
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.styles import Style
    except ImportError:
        return _open_editor_fallback(initial_loc, initial_msg)

    result: list[tuple[str, str] | None] = [None]
    title = f" Note #{note_id} " if note_id else " Nouvelle note "

    loc_area = TextArea(
        text=initial_loc, multiline=False, height=1,
        prompt="Lieu : ",
        style="class:loc-input",
    )
    msg_area = TextArea(
        text=initial_msg, multiline=True,
        scrollbar=True, style="class:msg-input",
        wrap_lines=True,
    )

    kb = KeyBindings()

    @kb.add("c-s")
    def _save(event):
        result[0] = (loc_area.text.strip(), msg_area.text.strip())
        event.app.exit()

    @kb.add("escape", eager=True)
    def _cancel(event):
        event.app.exit()

    # Tab : passe de loc_area à msg_area et vice-versa
    @kb.add("tab")
    def _tab(event):
        focus_map = {id(loc_area.control): msg_area, id(msg_area.control): loc_area}
        nxt = focus_map.get(id(event.app.layout.current_control))
        if nxt:
            event.app.layout.focus(nxt)

    layout = Layout(HSplit([
        Window(height=1,
               content=BufferControl(
                   buffer=Buffer(name="__title__", read_only=True,
                                 document=Document(title)),
               ),
               style="class:title"),
        Label(text="Lieu"),
        loc_area,
        Label(text="Message  (Ctrl+S = sauvegarder, Tab = changer de champ, Echap = annuler)"),
        msg_area,
    ]))

    app = Application(
        layout=layout, key_bindings=kb, full_screen=True,
        style=Style.from_dict({
            "title":     "reverse bold",
            "loc-input": "bg:#1c1c2e",
            "msg-input": "bg:#12121e",
        }),
    )
    try:
        app.run()
    except (KeyboardInterrupt, EOFError):
        return None
    return result[0]


def _open_editor_fallback(initial_loc: str, initial_msg: str) -> tuple[str, str] | None:
    """Saisie simple sans prompt_toolkit (fallback)."""
    try:
        loc = input(f"Lieu [{initial_loc}]: ").strip() or initial_loc
        console.print("[dim]Message (ligne vide pour terminer) :[/dim]")
        lines: list[str] = []
        while True:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                return None
            if not line:
                break
            lines.append(line)
        msg = "\n".join(lines) or initial_msg
        return (loc, msg)
    except (EOFError, KeyboardInterrupt):
        return None


# ── Sous-handlers ─────────────────────────────────────────────────────────────

def _cmd_list(loc_opt: str | None, ctx) -> None:
    from uexinfo.cache.notes_manager import NoteStore
    store = NoteStore()
    if loc_opt:
        loc_norm = _normalize_loc(loc_opt)
        notes    = store.list_by_location(loc_norm)
        _display_notes(notes, f"Notes — {loc_norm}", ctx)
    else:
        notes = store.list_all()
        _display_notes(notes, "Toutes les notes", ctx)


def _cmd_delete(rm_val: str, ctx) -> None:
    from uexinfo.cache.notes_manager import NoteStore
    store = NoteStore()
    if rm_val.lstrip("-").isdigit():
        note_id = int(rm_val)
        if store.delete_by_id(note_id):
            print_ok(f"Note #{note_id} supprimee.")
        else:
            print_warn(f"Note #{note_id} introuvable.")
    else:
        loc_norm = _normalize_loc(rm_val)
        count = store.delete_by_location(loc_norm)
        if count:
            print_ok(f"{count} note(s) supprimee(s) pour '{loc_norm}'.")
        else:
            print_warn(f"Aucune note pour '{loc_norm}'.")


def _cmd_add(loc: str, message: str, ctx) -> None:
    from uexinfo.cache.notes_manager import NoteStore
    note_id = NoteStore().add(loc, message)
    print_ok(f"Note #{note_id} ajoutee a '{loc}'.")


def _cmd_edit(loc: str, note_id: int | None, ctx) -> None:
    from uexinfo.cache.notes_manager import NoteStore
    store = NoteStore()

    # Overlay : déléguer au formulaire HTML
    pending = getattr(ctx, "_overlay_msgs", None)
    if pending is not None:
        initial = store.get(note_id) if note_id else None
        pending.append({
            "type":     "note_edit",
            "note_id":  note_id,
            "location": initial["location"] if initial else loc,
            "message":  initial["message"]  if initial else "",
        })
        return

    # CLI : éditeur TUI
    initial = store.get(note_id) if note_id else None
    init_loc = initial["location"] if initial else loc
    init_msg = initial["message"]  if initial else ""

    res = _open_editor(init_loc, init_msg, note_id)
    if res is None:
        print_warn("Edition annulee.")
        return
    new_loc, new_msg = res
    if not new_msg:
        print_warn("Message vide - annule.")
        return
    if note_id and initial:
        store.update(note_id, message=new_msg, location=new_loc or init_loc)
        print_ok(f"Note #{note_id} mise a jour.")
    else:
        nid = store.add(new_loc or loc, new_msg)
        print_ok(f"Note #{nid} ajoutee a '{new_loc or loc}'.")


# ── Handler principal ─────────────────────────────────────────────────────────

@register("note", "notes")
def cmd_note(args: list[str], ctx) -> None:
    """Notes personnelles par lieu."""
    opts = _parse_args(args)
    if opts is None:
        return

    loc_opt  = opts["location"]
    curr_loc = _current_loc(ctx)
    loc      = _normalize_loc(loc_opt) if loc_opt else curr_loc

    # Suppression
    if opts["rm"] is not None:
        _cmd_delete(opts["rm"], ctx)
        return

    # Listage seul
    if not opts["edit"] and opts["message"] is None:
        _cmd_list(loc_opt, ctx)
        return

    # Ajout direct (message présent, pas d'édition)
    if opts["message"] is not None and not opts["edit"]:
        if not loc:
            print_error("Lieu non defini - utilisez -l <lieu> ou /go from <lieu>.")
            return
        _cmd_add(loc, opts["message"], ctx)
        return

    # Édition (--edit)
    if not loc and not opts["note_id"]:
        print_error("Lieu non defini - utilisez -l <lieu> ou /go from <lieu>.")
        return
    _cmd_edit(loc, opts["note_id"], ctx)
