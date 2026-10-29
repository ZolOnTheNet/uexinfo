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
    """Date « JJ/MM/AAAA » d'un horodatage."""
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y")


def _normalize_loc(name: str) -> str:
    """Nom de lieu sous sa forme courte commune (underscores remplacés par des espaces)."""
    from uexinfo.cache.data_manager import _loc_short
    return _loc_short(name.replace("_", " ").strip()).strip()


def _current_loc(ctx) -> str:
    """Position actuelle du joueur sous forme courte, ou « » si inconnue."""
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


# ── Sous-handlers ─────────────────────────────────────────────────────────────

def _cmd_list(loc_opt: str | None, ctx) -> None:
    """Affiche les notes d'un lieu, ou toutes les notes si aucun lieu n'est donné."""
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
    """Supprime une note par son numéro, ou toutes les notes d'un lieu."""
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
    """Ajoute une note à un lieu."""
    from uexinfo.cache.notes_manager import NoteStore
    note_id = NoteStore().add(loc, message)
    print_ok(f"Note #{note_id} ajoutee a '{loc}'.")


def _cmd_edit(loc: str, note_id: int | None, ctx) -> None:
    """Ouvre le formulaire d'édition d'une note (ou d'une nouvelle) dans l'overlay."""
    from uexinfo.cache.notes_manager import NoteStore
    store = NoteStore()

    pending = getattr(ctx, "_overlay_msgs", None)
    if pending is None:
        ctx._overlay_msgs = []
        pending = ctx._overlay_msgs
    initial = store.get(note_id) if note_id else None
    pending.append({
        "type":     "note_edit",
        "note_id":  note_id,
        "location": initial["location"] if initial else loc,
        "message":  initial["message"]  if initial else "",
    })


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
