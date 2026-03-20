"""Commande /voyage — planification de voyages (ensemble de missions)."""
from __future__ import annotations

from rich.table import Table

from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section
from uexinfo.models.voyage import Voyage

# Sous-commandes reconnues
_SUBS = frozenset({
    "on", "off", "new", "list", "name", "clear",
    "add", "remove", "copy", "accept", "later", "cancel",
    # alias français
    "activer", "désactiver", "nouveau", "liste",
    "renommer", "effacer", "ajouter", "retirer", "supprimer",
    "valider", "garder", "annuler",
    # flag --trajets
    "--trajets",
})


@register("voyage", "v")
def cmd_voyage(args: list[str], ctx) -> None:
    """Planification de voyages (ensemble de missions)."""
    vm = ctx.voyage_manager
    voyage, sub, rest = _resolve(args, ctx)

    if not sub:
        # /voyage sans args → liste ou info
        if voyage:
            _cmd_show(voyage, ctx)
        else:
            _cmd_list(ctx)
        return

    if sub in ("on", "activer"):
        if voyage:
            vm.activate(str(voyage.id))
            print_ok(f"Voyage activé : [{C.UEX}]{voyage.name}[/{C.UEX}]")
        else:
            active = vm.get_active()
            if active:
                print_ok(f"Voyage déjà actif : [{C.UEX}]{active.name}[/{C.UEX}]")
            else:
                v = vm.new_voyage(departure=_player_loc(ctx))
                print_ok(f"Nouveau voyage créé et activé : [{C.UEX}]{v.name}[/{C.UEX}]")

    elif sub in ("off", "désactiver"):
        if not _require_active(vm):
            return
        vm.deactivate()
        print_ok("Voyage désactivé — conservé pour reprise ultérieure.")

    elif sub in ("new", "nouveau"):
        name = " ".join(rest) if rest else None
        v = vm.new_voyage(name=name, departure=_player_loc(ctx))
        print_ok(f"Nouveau voyage créé et activé : [{C.UEX}]{v.name}[/{C.UEX}]  "
                 f"[{C.DIM}](#{v.id})[/{C.DIM}]")

    elif sub in ("name", "renommer"):
        target = voyage or vm.get_active()
        if not target:
            _no_active()
            return
        if not rest:
            print_error("Nom manquant : /voyage name <nouveau_nom>")
            return
        old = target.name
        target.name = " ".join(rest)
        vm.update(target)
        print_ok(f"Renommé : {old} → [{C.UEX}]{target.name}[/{C.UEX}]")

    elif sub in ("list", "liste"):
        if "--trajets" in args or (voyage is None and vm.get_active() is None):
            _cmd_list(ctx)
        else:
            target = voyage or vm.get_active()
            if target:
                _cmd_show(target, ctx)
            else:
                _cmd_list(ctx)

    elif sub in ("clear", "effacer"):
        target = voyage or vm.get_active()
        if not target:
            _no_active()
            return
        n = len(target.mission_ids)
        target.mission_ids.clear()
        vm.update(target)
        print_ok(f"{n} mission(s) retirée(s) du voyage [{C.UEX}]{target.name}[/{C.UEX}]")

    elif sub in ("add", "ajouter"):
        target = voyage or vm.get_active()
        if not target:
            _no_active()
            return
        _cmd_add(rest, target, ctx)

    elif sub in ("remove", "retirer", "supprimer"):
        target = voyage or vm.get_active()
        if not target:
            _no_active()
            return
        _cmd_remove(rest, target, ctx)

    elif sub == "copy":
        source = voyage or vm.get_active()
        if not source:
            _no_active()
            return
        dest_ref = rest[0] if rest else None
        new_v = vm.copy_to(source, dest_ref)
        print_ok(f"Copié vers : [{C.UEX}]{new_v.name}[/{C.UEX}]  [{C.DIM}](#{new_v.id})[/{C.DIM}]")

    elif sub in ("accept", "valider"):
        target = voyage or vm.get_active()
        if not target:
            _no_active()
            return
        _cmd_show(target, ctx)
        _run_analysis(target, ctx)
        if not voyage:  # ne désactive que si c'était le voyage actif
            vm.deactivate()

    elif sub in ("later", "garder"):
        if vm.get_active():
            vm.deactivate()
            print_ok("Voyage sauvegardé. Reprenez avec /voyage on ou /voyage <nom>.")

    elif sub in ("cancel", "annuler"):
        # Recharge depuis le disque (état précédent)
        vm._load()
        print_warn("Modifications annulées — retour à la dernière sauvegarde.")

    else:
        _show_help()


# ── Résolution voyage + sous-commande ────────────────────────────────────────

def _resolve(args: list[str], ctx) -> tuple[Voyage | None, str, list[str]]:
    """
    Analyse les args :
      - Flag -n<ref> ou -n <ref> → voyage explicite
      - Premier token non-sous-commande correspondant à un voyage → voyage explicite
      - Token suivant (ou premier si voyage résolu) = sous-commande
    Retourne (voyage_cible | None, sous_commande | "", args_restants).
    """
    vm = ctx.voyage_manager
    voyage: Voyage | None = None
    cleaned = list(args)

    # Chercher -n flag
    i = 0
    while i < len(cleaned):
        a = cleaned[i]
        if a == "-n" and i + 1 < len(cleaned):
            voyage = vm.get(cleaned[i + 1])
            cleaned = cleaned[:i] + cleaned[i + 2:]
            break
        if a.startswith("-n") and len(a) > 2:
            voyage = vm.get(a[2:])
            cleaned = cleaned[:i] + cleaned[i + 1:]
            break
        i += 1

    if not cleaned:
        return voyage, "", []

    # Premier token : est-ce une référence de voyage ou une sous-commande ?
    first = cleaned[0].lower()
    if first not in _SUBS and voyage is None:
        candidate = vm.get(cleaned[0])
        if candidate:
            voyage = candidate
            cleaned = cleaned[1:]

    if not cleaned:
        return voyage, "", []

    sub = cleaned[0].lower()
    rest = cleaned[1:]

    if sub in _SUBS:
        return voyage, sub, rest

    # Pas reconnu
    return voyage, sub, rest


# ── Affichage liste de voyages ────────────────────────────────────────────────

def _cmd_list(ctx) -> None:
    vm = ctx.voyage_manager
    mm = ctx.mission_manager
    if not vm.voyages:
        print_warn("Aucun voyage enregistré")
        console.print(f"[{C.DIM}]/voyage new [nom]  pour créer un voyage[/{C.DIM}]")
        return

    section("Voyages")

    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("#",        style=C.DIM,    width=3,  justify="right")
    tbl.add_column("*",        width=2)
    tbl.add_column("Nom",      style=C.LABEL,  max_width=18)
    tbl.add_column("Miss.",    justify="right", width=6)
    tbl.add_column("SCU",      justify="right", width=6)
    tbl.add_column("Récomp.",  justify="right", width=13)
    tbl.add_column("Départ",   style=C.UEX,    max_width=14)
    tbl.add_column("→",        style=C.DIM,    width=1)
    tbl.add_column("Arrivée",  style=C.UEX,    max_width=14)
    tbl.add_column("Session",  style=C.DIM,    width=7)

    for v in vm.voyages:
        is_active = v.id == vm.active_id
        bullet = f"[{'yellow' if is_active else C.DIM}]●[/{'yellow' if is_active else C.DIM}]"
        missions = [mm.get(str(mid)) for mid in v.mission_ids]
        missions = [m for m in missions if m]
        n_miss = len(missions)
        total_scu = sum(m.total_scu for m in missions)
        total_rew = sum(m.reward_uec for m in missions)
        rew_str = f"{total_rew:,}".replace(",", " ") + " aUEC"
        scu_str = f"{total_scu:.0f}□" if total_scu else "—"
        dep = v.departure or "—"
        arr = v.arrival or _infer_arrival(missions) or "—"

        tbl.add_row(
            str(v.id), bullet, v.name,
            f"{n_miss}m", scu_str, rew_str,
            dep, "→", arr,
            f"S{v.session_id}",
        )

    console.print(tbl)
    console.print(
        f"\n[{C.DIM}]Double-clic sur un nom → afficher  ·  "
        f"Clic droit → menu (Activer, Analyser…)[/{C.DIM}]"
    )
    console.print(f"[{C.DIM}]/voyage new  ·  /voyage <nom>  ·  /voyage on[/{C.DIM}]")


# ── Affichage missions d'un voyage ────────────────────────────────────────────

def _cmd_show(voyage: Voyage, ctx) -> None:
    vm = ctx.voyage_manager
    mm = ctx.mission_manager
    is_active = voyage.id == vm.active_id
    active_label = f"  [yellow]●[/yellow]" if is_active else ""

    dep = voyage.departure or "?"
    arr = voyage.arrival or _infer_arrival(
        [m for m in (mm.get(str(mid)) for mid in voyage.mission_ids) if m]
    ) or "?"

    section(f"Voyage : {voyage.name}{active_label}")
    console.print(
        f"  [{C.DIM}]Départ : [{C.UEX}]{dep}[/{C.UEX}]  →  Arrivée : [{C.UEX}]{arr}[/{C.UEX}][/{C.DIM}]"
    )

    if not voyage.mission_ids:
        print_warn("Aucune mission dans ce voyage")
        console.print(f"[{C.DIM}]/voyage add <id|nom>  pour ajouter des missions[/{C.DIM}]")
        return

    graph = ctx.cache.transport_graph

    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("#",          style=C.DIM,    width=3,  justify="right")
    tbl.add_column("Nom",        style=C.LABEL,  max_width=22)
    tbl.add_column("Départ",     style=C.UEX,    max_width=16)
    tbl.add_column("→",          style=C.DIM,    width=1)
    tbl.add_column("Arrivée",    style=C.UEX,    max_width=16)
    tbl.add_column("Dist",       justify="right", width=7)
    tbl.add_column("SCU",        justify="right", width=4)
    tbl.add_column("Récompense", justify="right", width=12)
    tbl.add_column("Tags",       width=6)

    total_scu = 0.0
    total_rew = 0

    for mid in voyage.mission_ids:
        m = mm.get(str(mid))
        if not m:
            tbl.add_row(str(mid), f"[{C.WARNING}]mission #{mid} introuvable[/{C.WARNING}]",
                        "—", "→", "—", "—", "—", "—", "")
            continue

        srcs = ", ".join(m.all_sources[:2]) or "—"
        dsts = ", ".join(m.all_destinations[:2]) or "—"
        scu_str = f"{m.total_scu:.0f}□" if m.total_scu else "—"
        rew_str = f"{m.reward_uec:,}".replace(",", " ") + " aUEC"
        total_scu += m.total_scu
        total_rew += m.reward_uec

        # Synergies depuis manager
        tags = " ".join(mm.synergies_for_voyage(m, voyage.mission_ids))

        dist_str = "?"
        if m.all_sources and m.all_destinations:
            try:
                result = graph.shortest_path(m.all_sources[0], m.all_destinations[0])
                if result:
                    d = result.total_distance
                    dist_str = f"{d:.1f}Gm" if d >= 1 else f"{d*1000:.0f}Mm"
            except Exception:
                pass

        has_delay = any(o.time_cost for o in m.objectives)
        name_label = m.name + (f" [{C.WARNING}]⏱[/{C.WARNING}]" if has_delay else "")

        tbl.add_row(str(mid), name_label, srcs, "→", dsts, dist_str, scu_str, rew_str, tags)

    console.print(tbl)

    rew_str = f"{total_rew:,}".replace(",", " ")
    console.print(
        f"\n[{C.DIM}]{len(voyage.mission_ids)} mission(s) · "
        f"[bold]{total_scu:.0f}[/bold] SCU · "
        f"[bold]{rew_str}[/bold] aUEC[/{C.DIM}]"
    )
    if is_active:
        console.print(
            f"[{C.DIM}]/voyage add <m>  ·  /voyage remove <m>  ·  "
            f"/voyage accept  ·  /voyage off[/{C.DIM}]"
        )


# ── Add missions ──────────────────────────────────────────────────────────────

def _cmd_add(args: list[str], voyage: Voyage, ctx) -> None:
    vm = ctx.voyage_manager
    mm = ctx.mission_manager

    if not args:
        # Afficher le catalogue pour référence
        console.print(f"[{C.DIM}]Catalogue des missions :[/{C.DIM}]")
        if not mm.missions:
            print_warn("Catalogue vide — /mission add pour créer des missions")
            return
        for m in mm.missions:
            in_v = "✓" if m.id in voyage.mission_ids else " "
            srcs = "→".join(filter(None, m.all_sources[:1] + m.all_destinations[:1])) or "—"
            console.print(
                f"  [{C.DIM}][{in_v}][/{C.DIM}] "
                f"[{C.LABEL}]#{m.id}[/{C.LABEL}]  "
                f"[bold]{m.name}[/bold]  "
                f"[{C.DIM}]{srcs}  {m.reward_uec:,} aUEC[/{C.DIM}]"
            )
        console.print(f"[{C.DIM}]/voyage add <id> [id2 ...]  pour ajouter[/{C.DIM}]")
        return

    added = []
    not_found = []
    for ref in args:
        m = mm.get(ref)
        if not m:
            not_found.append(ref)
            continue
        n = vm.add_missions(voyage, [m.id])
        if n:
            added.append(m.name)

    if added:
        print_ok(f"Ajouté(s) à [{C.UEX}]{voyage.name}[/{C.UEX}] : {', '.join(added)}")
    if not_found:
        print_warn(f"Mission(s) introuvable(s) : {', '.join(not_found)}")
    if not added and not not_found:
        console.print(f"[{C.DIM}]Toutes ces missions sont déjà dans le voyage.[/{C.DIM}]")


# ── Remove mission ────────────────────────────────────────────────────────────

def _cmd_remove(args: list[str], voyage: Voyage, ctx) -> None:
    vm = ctx.voyage_manager
    mm = ctx.mission_manager
    if not args:
        print_error("Identifiant de mission manquant")
        return
    for ref in args:
        m = mm.get(ref)
        if not m:
            print_warn(f"Mission introuvable : {ref}")
            continue
        if vm.remove_mission(voyage, m.id):
            print_ok(f"Retiré de [{C.UEX}]{voyage.name}[/{C.UEX}] : {m.name}")
        else:
            print_warn(f"{m.name} n'est pas dans ce voyage")


# ── Analyse (Phase 1 basique) ─────────────────────────────────────────────────

def _run_analysis(voyage: Voyage, ctx) -> None:
    mm = ctx.mission_manager
    missions = [m for m in (mm.get(str(mid)) for mid in voyage.mission_ids) if m]
    if not missions:
        print_warn("Aucune mission à analyser")
        return

    section(f"Analyse — {voyage.name}")

    # Lieux uniques
    locs: dict[str, None] = {}
    for m in missions:
        for loc in m.all_sources + m.all_destinations:
            locs[loc] = None
    console.print(f"  [{C.DIM}]Lieux impliqués : {len(locs)}[/{C.DIM}]")
    for loc in locs:
        console.print(f"    [{C.LABEL}]{loc}[/{C.LABEL}]")

    total_scu = sum(m.total_scu for m in missions)
    total_rew = sum(m.reward_uec for m in missions)
    rew_str = f"{total_rew:,}".replace(",", " ")
    console.print(f"\n  [bold]Total :[/bold]  {len(missions)} mission(s)  ·  {total_scu:.0f} SCU  ·  {rew_str} aUEC")

    # Suggestion vaisseau
    player = ctx.player
    if player.ships:
        suitable = [s for s in player.ships if (s.scu or 0) >= total_scu]
        if suitable:
            best = min(suitable, key=lambda s: s.scu or 0)
            console.print(f"\n  [bold]Vaisseau suggéré :[/bold] [{C.UEX}]{best.name}[/{C.UEX}]  [{C.DIM}]{best.scu} SCU[/{C.DIM}]")
        else:
            biggest = max(player.ships, key=lambda s: s.scu or 0)
            print_warn(f"Aucun vaisseau assez grand ({total_scu:.0f} SCU requis)")
            console.print(f"  [{C.DIM}]Plus grand disponible : {biggest.name} ({biggest.scu} SCU)[/{C.DIM}]")

    console.print(f"\n[{C.DIM}]⚠ Optimisation de route — Phase 3[/{C.DIM}]")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _player_loc(ctx) -> str | None:
    return (getattr(ctx.player, "location", None) or "").strip() or None


def _infer_arrival(missions) -> str | None:
    """Déduit la destination finale depuis la dernière mission."""
    for m in reversed(missions):
        if m.all_destinations:
            return m.all_destinations[-1]
    return None


def _require_active(vm) -> bool:
    if not vm.get_active():
        print_warn("Aucun voyage actif")
        console.print(f"[{C.DIM}]/voyage on  ou  /voyage new  pour démarrer[/{C.DIM}]")
        return False
    return True


def _no_active() -> None:
    print_warn("Aucun voyage actif")
    from uexinfo.display.formatter import console as _c
    _c.print(f"[dim]/voyage on  ou  /voyage new  pour démarrer[/dim]")


# ── Aide ──────────────────────────────────────────────────────────────────────

def _show_help() -> None:
    section("Aide — /voyage")
    lines = [
        ("on",              "Active le dernier voyage ou en crée un nouveau"),
        ("off",             "Désactive le voyage courant (conservé)"),
        ("new [nom]",       "Crée un nouveau voyage + l'active"),
        ("<nom|n>",         "Active le voyage (ou /voyage <nom> list pour afficher)"),
        ("name <nom>",      "Renomme le voyage actif"),
        ("list [--trajets]","Missions du voyage actif, ou tous les voyages"),
        ("add [m1 m2...]",  "Ajoute des missions (catalogue) au voyage actif"),
        ("remove <m>",      "Retire une mission du voyage"),
        ("clear",           "Vide les missions du voyage actif"),
        ("copy [n|nom]",    "Copie/fusionne vers un autre voyage"),
        ("accept",          "Valide + analyse, désactive le voyage"),
        ("later",           "Sauvegarde sans analyse, désactive"),
        ("cancel",          "Annule les modifications (retour à la dernière sauvegarde)"),
    ]
    for cmd, desc in lines:
        console.print(f"  [bold {C.LABEL}]/voyage {cmd:<22}[/bold {C.LABEL}]  [{C.DIM}]{desc}[/{C.DIM}]")
    console.print()
    console.print(f"  [{C.DIM}]Adressage : /voyage 2 list   -n2 list   -n toto list[/{C.DIM}]")
    console.print(f"  [{C.DIM}]Alias : /v  ·  Double-clic = afficher  ·  Clic droit = Activer/Analyser…[/{C.DIM}]")
