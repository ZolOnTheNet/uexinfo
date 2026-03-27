"""Commande /dev — mode développeur.

Contourne les comportements de production pour faciliter les tests :
  - Import batch de screenshots historiques dans la ScreenshotDB
  - Vidage de la DB
  - Statistiques de la DB
  - Toggle persistant du mode dev

Ces fonctions ne sont pas disponibles via /scan ou /mission car elles
ignorent volontairement des garde-fous (watcher, déduplication, etc.).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import uexinfo.config.settings as settings
from uexinfo.cli.commands import register
from uexinfo.display.formatter import (
    console, print_error, print_ok, print_warn, print_info, section,
)
from uexinfo.display import colors as C

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_dev_mode(ctx) -> bool:
    """True si le mode développeur est activé dans la config."""
    return bool(ctx.cfg.get("dev", {}).get("enabled", False))


def _get_db(ctx):
    """Retourne la ScreenshotDB (crée si absente du ctx)."""
    db = getattr(ctx, "screenshot_db", None)
    if db is None:
        try:
            from uexinfo.cache.screenshot_db import ScreenshotDB
            db = ScreenshotDB()
            ctx.screenshot_db = db
        except Exception as e:
            print_error(f"Impossible d'accéder à la ScreenshotDB : {e}")
            return None
    return db


# ── Commande principale ───────────────────────────────────────────────────────

@register("dev")
def cmd_dev(args: list[str], ctx) -> None:
    """Mode développeur — bypass des comportements de production.

    /dev                            Statut du mode dev et de la DB
    /dev on|off                     Activer/désactiver (persisté)
    /dev scan import <dossier>      Importer tous les screenshots d'un dossier
    /dev scan import <dossier> all  Réimporter même les fichiers déjà traités
    /dev scan clear                 Vider la screenshot_db
    /dev db                         Statistiques et contenu de la screenshot_db
    /dev db list [n]                Lister les n dernières entrées (défaut 20)
    """
    if not args:
        _status(ctx)
        return

    sub = args[0].lower()

    if sub in ("on", "off"):
        _toggle(sub == "on", ctx)
        return

    if sub == "scan":
        sub2 = args[1].lower() if len(args) >= 2 else ""
        if sub2 == "import":
            rest = args[2:]
            # Détecter le flag "all" en fin ou début de la liste restante
            force_reimport = "all" in [a.lower() for a in rest]
            path_parts = [a for a in rest if a.lower() != "all"]
            folder_str = " ".join(path_parts).strip("\"'")
            _scan_import(folder_str, ctx, force_reimport=force_reimport)
        elif sub2 == "clear":
            _scan_clear(ctx)
        else:
            print_error(
                "Usage : /dev scan import <dossier> [all]  |  /dev scan clear"
            )
        return

    if sub == "db":
        sub2 = args[1].lower() if len(args) >= 2 else ""
        if sub2 == "list":
            n = 20
            if len(args) >= 3:
                try:
                    n = int(args[2])
                except ValueError:
                    print_error("n doit être un entier")
                    return
            _db_list(ctx, n)
        else:
            _db_stats(ctx)
        return

    print_error(
        f"Sous-commande inconnue : {sub}  —  /dev [on|off|scan|db]"
    )


# ── Sous-commandes ────────────────────────────────────────────────────────────

def _status(ctx) -> None:
    enabled = is_dev_mode(ctx)
    db = _get_db(ctx)
    total = len(db) if db else 0

    tag = "[bold yellow]ON[/bold yellow]" if enabled else f"[{C.DIM}]OFF[/{C.DIM}]"
    console.print(f"\n[bold]Mode DEV[/bold] : {tag}   ScreenshotDB : {total} entrée(s)")
    if not enabled:
        console.print(f"[{C.DIM}]  /dev on  pour activer[/{C.DIM}]")
    console.print(
        f"\n[{C.DIM}]"
        f"/dev scan import <dossier>   importer screenshots historiques\n"
        f"/dev scan import <dossier> all   réimporter même les déjà traités\n"
        f"/dev scan clear              vider la DB\n"
        f"/dev db                      statistiques de la DB"
        f"[/{C.DIM}]"
    )


def _toggle(enable: bool, ctx) -> None:
    ctx.cfg.setdefault("dev", {})["enabled"] = enable
    settings.save(ctx.cfg)
    if enable:
        print_ok("Mode DEV activé")
        console.print(
            f"[{C.DIM}]  Bypass : watcher, déduplication OCR, import historique[/{C.DIM}]"
        )
    else:
        print_ok("Mode DEV désactivé")


def _scan_import(folder_str: str, ctx, force_reimport: bool = False) -> None:
    """Importe tous les screenshots d'un dossier dans la screenshot_db via OCR.

    Contourne le ScreenshotWatcher (qui ignore les fichiers existants au
    démarrage) pour permettre le traitement de captures historiques.

    Politique de skip (sans force_reimport) :
      - Sauter les entrées de type mission/terminal/* déjà résolues
      - Retenter les entrées de type unknown/pending (OCR ayant échoué)
      - Traiter les fichiers absents de la DB

    force_reimport=True : tout retraiter sans exception.
    """
    from uexinfo.cli.commands.scan import _scan_image_file
    from uexinfo.models.mission_result import MissionResult

    # Types considérés comme "bien résolus" → on ne les retente pas
    _SKIP_TYPES = {"mission", "terminal_buy", "terminal_sell", "terminal"}

    if not folder_str:
        print_error("Usage : /dev scan import <dossier>")
        return

    folder = Path(folder_str)
    if not folder.is_dir():
        candidate = Path.cwd() / folder_str
        if candidate.is_dir():
            folder = candidate
        else:
            print_error(f"Dossier introuvable : {folder_str}")
            return

    images = sorted(
        (p for p in folder.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES),
        key=lambda p: p.stat().st_mtime,
    )
    if not images:
        print_warn(f"Aucun fichier image dans : {folder}")
        return

    db = _get_db(ctx)

    # ── Diagnostic pre-import ─────────────────────────────────────────────────
    by_status: dict[str, int] = {"absent": 0, "unknown": 0, "resolved": 0}
    for p in images:
        if db is None:
            by_status["absent"] += 1
        else:
            e = db.get(p.name)
            if e is None:
                by_status["absent"] += 1
            elif e.type in _SKIP_TYPES:
                by_status["resolved"] += 1
            else:
                by_status["unknown"] += 1   # "unknown" ou "pending"

    to_process = (
        len(images) if force_reimport
        else by_status["absent"] + by_status["unknown"]
    )

    section(f"DEV — Import batch : {folder.name}")
    console.print(
        f"[{C.DIM}]{len(images)} fichier(s)  │  "
        f"{by_status['absent']} nouveau(x)  │  "
        f"{by_status['unknown']} à retenter (unknown)  │  "
        f"{by_status['resolved']} déjà résolus (mission/terminal)"
        + ("  [force_reimport=all]" if force_reimport else "")
        + f"[/{C.DIM}]"
    )
    if by_status["resolved"] and not force_reimport:
        console.print(
            f"[{C.DIM}]  → ajoutez [bold]all[/bold] pour forcer la réimportation des résolus[/{C.DIM}]"
        )
    console.print()

    # ── Import ────────────────────────────────────────────────────────────────
    ok_mission = ok_terminal = ok_other = skipped = errors = 0

    for i, img_path in enumerate(images, 1):
        entry = db.get(img_path.name) if db else None
        if not force_reimport and entry is not None and entry.type in _SKIP_TYPES:
            skipped += 1
            continue

        retry_tag = f"  [{C.DIM}](retentative {entry.type})[/{C.DIM}]" if (
            entry is not None and entry.type not in _SKIP_TYPES and entry.type != "pending"
        ) else ""
        console.print(
            f"  [{C.DIM}][{i}/{len(images)}][/{C.DIM}]  "
            f"[{C.LABEL}]{img_path.name}[/{C.LABEL}]{retry_tag}"
        )
        try:
            result = _scan_image_file(ctx, img_path)
            if result is None:
                errors += 1
                console.print(f"    [{C.WARNING}]— non reconnu[/{C.WARNING}]")
            elif isinstance(result, MissionResult):
                ok_mission += 1
                console.print(f"    [{C.SUCCESS}]✓ mission[/{C.SUCCESS}]")
            else:
                ok_terminal += 1
                console.print(f"    [{C.DIM}]✓ terminal[/{C.DIM}]")
        except Exception as e:
            errors += 1
            console.print(f"    [{C.ERROR}]✗ {e}[/{C.ERROR}]")

    total_ok = ok_mission + ok_terminal + ok_other
    console.print(
        f"\n[{C.DIM}]Terminé — "
        f"{ok_mission} mission(s)  "
        f"{ok_terminal} terminal(s)  "
        f"{skipped} ignoré(s)  "
        f"{errors} non reconnu(s)[/{C.DIM}]"
    )
    if ok_mission > 0:
        console.print(
            f"[{C.DIM}]→ /mission scan all  pour consulter les missions importées[/{C.DIM}]"
        )
    if errors > 0 and not force_reimport:
        console.print(
            f"[{C.DIM}]→ /dev scan import <dossier> all  pour forcer la réimportation de tous[/{C.DIM}]"
        )


def _scan_clear(ctx) -> None:
    """Vide la screenshot_db (supprime le fichier JSON)."""
    from uexinfo.cache.screenshot_db import _DB_PATH
    if _DB_PATH.exists():
        try:
            _DB_PATH.unlink()
            ctx.screenshot_db = None
            print_ok(f"ScreenshotDB supprimée ({_DB_PATH.name})")
        except Exception as e:
            print_error(f"Erreur : {e}")
    else:
        print_warn("ScreenshotDB déjà vide (fichier inexistant)")


def _db_stats(ctx) -> None:
    """Affiche les statistiques générales de la screenshot_db."""
    db = _get_db(ctx)
    if db is None:
        return

    entries = db.all()
    if not entries:
        print_warn("ScreenshotDB vide")
        console.print(f"[{C.DIM}]→ /dev scan import <dossier>  pour importer des screenshots[/{C.DIM}]")
        return

    # Comptage par type
    by_type: dict[str, int] = {}
    for e in entries:
        by_type[e.type] = by_type.get(e.type, 0) + 1

    section(f"ScreenshotDB — {len(entries)} entrée(s)")
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
        bar = "█" * min(n, 20)
        console.print(f"  [{C.LABEL}]{t:<22}[/{C.LABEL}] [{C.DIM}]{bar}[/{C.DIM}] {n}")

    # Plage temporelle
    first = datetime.fromtimestamp(entries[0].file_mtime).strftime("%Y-%m-%d %H:%M")
    last  = datetime.fromtimestamp(entries[-1].file_mtime).strftime("%Y-%m-%d %H:%M")
    console.print(f"\n[{C.DIM}]Période : {first} → {last}[/{C.DIM}]")
    console.print(f"[{C.DIM}]/dev db list [n]  pour voir les entrées[/{C.DIM}]")


def _db_list(ctx, n: int = 20) -> None:
    """Liste les n dernières entrées de la screenshot_db."""
    db = _get_db(ctx)
    if db is None:
        return

    entries = db.all()
    if not entries:
        print_warn("ScreenshotDB vide")
        return

    shown = entries[-n:]
    section(f"ScreenshotDB — {len(shown)} dernière(s) sur {len(entries)}")
    for e in shown:
        ts    = datetime.fromtimestamp(e.file_mtime).strftime("%Y-%m-%d %H:%M")
        title = (e.data.get("title") or e.data.get("terminal") or "")[:35]
        console.print(
            f"  [{C.DIM}]{ts}[/{C.DIM}]"
            f"  [{C.LABEL}]{e.type:<18}[/{C.LABEL}]"
            f"  [{C.DIM}]{e.file:<35}[/{C.DIM}]"
            + (f"  {title}" if title else "")
        )
