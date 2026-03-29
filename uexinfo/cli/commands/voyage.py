"""Commande /voyage — planification de voyages (ensemble de missions)."""
from __future__ import annotations

import sys

from rich.table import Table

from uexinfo.cli.commands import register
from uexinfo.cli.selector import SelectItem, pick
from uexinfo.display import colors as C
from uexinfo.display.adaptive import ColSpec, adaptive_table
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section
from uexinfo.models.voyage import Voyage

# ── Constantes calc ───────────────────────────────────────────────────────────
_UNKNOWN_DIST_PENALTY = 500.0  # Gm — pénalité si distance inconnue/injoignable
_CHAIN_BONUS_GM       = 2.0    # Gm soustraits si deux missions s'enchaînent (0 transit)
_GAP_WARN_GM          = 3.0    # Transit > N Gm → ⚠ dans le tableau de résultat

# Sous-commandes reconnues
_SUBS = frozenset({
    "on", "off", "new", "calc", "list", "name", "clear", "delete", "del",
    "add", "remove", "copy", "accept", "later", "cancel",
    "+",   # sauvegarder une proposition du dernier calc
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
        # /voyage on <ref> → activer le voyage donné
        if voyage is None and rest:
            voyage = vm.get(rest[0])
            if voyage is None:
                print_warn(f"Voyage introuvable : {rest[0]}")
                return
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

    elif sub == "calc":
        if not rest or rest[0].lower() in ("aide", "help", "?", "--help"):
            _show_calc_help(ctx)
        elif rest[0].lower() not in _AUTO_CRITERIA:
            print_warn(f"Critère inconnu : {rest[0]!r}")
            _show_calc_help(ctx)
        else:
            _cmd_new_auto(rest[0].lower(), rest[1:], ctx)

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

    elif sub in ("delete", "del", "supprimer"):
        _cmd_delete(rest, ctx)

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

    elif sub == "+":
        _cmd_save_proposal(rest, ctx)

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

    # Colonnes fixes : # 3, → 1, Dist 7, SCU 4, Récompense 12, Tags 6 = 33
    # Colonnes flexibles : Nom (poids 2) / Départ (poids 1) / Arrivée (poids 1)
    tbl = adaptive_table([
        ColSpec("#",          width=3,  justify="right", style=C.DIM),
        ColSpec("Nom",        flex=2,   min_flex=14,     style=C.LABEL),
        ColSpec("Départ",     flex=1,   min_flex=10,     style=C.UEX),
        ColSpec("→",          width=1,                   style=C.DIM),
        ColSpec("Arrivée",    flex=1,   min_flex=10,     style=C.UEX),
        ColSpec("Dist",       width=7,  justify="right"),
        ColSpec("SCU",        width=4,  justify="right"),
        ColSpec("Récompense", width=12, justify="right"),
        ColSpec("Tags",       width=6),
    ])

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
                result = graph.find_shortest_path(m.all_sources[0], m.all_destinations[0])
                if result is not None and result.total_distance is not None:
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
        if not mm.missions:
            print_warn("Catalogue vide — /mission add pour créer des missions")
            return
        items = [
            SelectItem(
                label    = f"#{m.id}  {m.name}",
                value    = m,
                meta     = (
                    "→".join(filter(None, m.all_sources[:1] + m.all_destinations[:1])) or "—"
                ) + f"  {m.reward_uec:,} aUEC",
                selected = m.id in voyage.mission_ids,
            )
            for m in mm.missions
        ]
        chosen = pick(ctx, items,
                      title=f"Missions → {voyage.name}",
                      mode="multi",
                      confirm_label="✓ Ajouter")
        if chosen is None:
            print_warn("Annulé.")
            return
        to_add = [it.value.id for it in chosen
                  if it.value.id not in voyage.mission_ids]
        if to_add:
            n = vm.add_missions(voyage, to_add)
            added_names = ", ".join(
                mm.get(str(mid)).name for mid in to_add if mm.get(str(mid))
            )
            print_ok(f"{n} mission(s) ajoutée(s) à [{C.UEX}]{voyage.name}[/{C.UEX}] : {added_names}")
        else:
            console.print(f"[{C.DIM}]Aucune nouvelle mission sélectionnée.[/{C.DIM}]")
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


# ── Suppression de voyages ────────────────────────────────────────────────────

def _cmd_delete(args: list[str], ctx) -> None:
    vm = ctx.voyage_manager
    if not vm.voyages:
        print_warn("Aucun voyage enregistré")
        return

    # --all → tout supprimer après confirmation
    if "--all" in args:
        n = len(vm.voyages)
        vm.voyages.clear()
        vm.active_id = None
        vm.save()
        print_ok(f"{n} voyage(s) supprimé(s)")
        return

    # Références explicites passées en argument
    if args:
        deleted, not_found = [], []
        for ref in args:
            v = vm.get(ref)
            if v:
                vm.remove(str(v.id))
                deleted.append(v.name)
            else:
                not_found.append(ref)
        if deleted:
            print_ok(f"Supprimé(s) : {', '.join(deleted)}")
        if not_found:
            print_warn(f"Introuvable(s) : {', '.join(not_found)}")
        return

    # Sans argument → sélecteur multi
    items = [
        SelectItem(
            label    = f"#{v.id}  {v.name}",
            value    = v,
            meta     = (
                f"{len(v.mission_ids)} mission(s)"
                + (f" · départ {v.departure}" if v.departure else "")
                + (" [actif]" if v.id == vm.active_id else "")
            ),
            selected = False,
        )
        for v in vm.voyages
    ]
    chosen = pick(ctx, items,
                  title="Supprimer des voyages",
                  mode="multi",
                  confirm_label="✕ Supprimer")
    if chosen is None:
        print_warn("Annulé.")
        return
    if not chosen:
        console.print(f"[{C.DIM}]Aucun voyage sélectionné.[/{C.DIM}]")
        return
    deleted = []
    for it in chosen:
        vm.remove(str(it.value.id))
        deleted.append(it.value.name)
    print_ok(f"{len(deleted)} voyage(s) supprimé(s) : {', '.join(deleted)}")


# ── Création automatique de voyage ────────────────────────────────────────────

# Critères reconnus (clé normalisée → libellé)
_AUTO_CRITERIA: dict[str, str] = {
    "court":    "Distance minimale",
    "dist":     "Distance minimale",
    "distance": "Distance minimale",
    "benefice": "Bénéfice maximal",
    "bénéfice": "Bénéfice maximal",
    "benef":    "Bénéfice maximal",
    "bénef":    "Bénéfice maximal",
    "roi":      "Meilleur ROI (aUEC/Gm)",
    "all":      "Toutes propositions",
    "tous":     "Toutes propositions",
}

_SINGLE_CRITERIA = ["dist", "benefice", "roi"]

# Mots-clés identifiant une station spatiale (heuristique)
_STATION_KW = {
    "station", "harbor", "port", "terminal", "refinery",
    "gateway", "hub", "relay", "beacon", "platform",
    "outpost", "warehouse", "depot",
}


def _loc_is_station(loc: str) -> bool:
    l = loc.lower()
    return any(kw in l for kw in _STATION_KW)


def _parse_auto_opts(args: list[str]) -> dict:
    """Extrait les options --xxx des arguments bruts."""
    opts: dict = {
        "boucle":       False,
        "todest":       None,
        "to":           [],
        "exclude":      [],
        "station":      False,
        "ship":         None,    # nom de vaisseau explicite
        "com":          False,
        "favoris":      False,
        "max_missions": 5,       # taille max du sous-ensemble sélectionné
    }
    i = 0
    while i < len(args):
        a = args[i].lower()
        if a in ("--boucle", "--blc"):
            opts["boucle"] = True
        elif a == "--station":
            opts["station"] = True
        elif a == "--com":
            opts["com"] = True
        elif a == "--favoris":
            opts["favoris"] = True
        elif a.startswith("--ship:"):
            opts["ship"] = args[i][7:]
        elif a == "--ship" and i + 1 < len(args):
            i += 1
            opts["ship"] = args[i]
        elif a.startswith("--max:"):
            try:
                opts["max_missions"] = max(1, int(args[i][6:]))
            except ValueError:
                pass
        elif a == "--max" and i + 1 < len(args):
            i += 1
            try:
                opts["max_missions"] = max(1, int(args[i]))
            except ValueError:
                pass
        elif a == "--todest" and i + 1 < len(args):
            i += 1
            opts["todest"] = args[i].replace("_", " ")
        elif a == "--to" and i + 1 < len(args):
            i += 1
            opts["to"].append(args[i].replace("_", " "))
        elif a == "--exclude" and i + 1 < len(args):
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                opts["exclude"].append(args[i].replace("_", " "))
                i += 1
            continue
        i += 1
    return opts


# ── Pré-filtrage (Option C) ───────────────────────────────────────────────────
_PREFILTER_THRESHOLD = 15   # si n > threshold → pré-filtrer avant brute-force
_PREFILTER_KEEP      = 15   # nombre de candidats conservés après pré-filtrage


def _prefilter_score(m, start_node: str | None, resolved: dict, dist: dict) -> float:
    """Score rapide d'une mission pour pré-sélection : reward / distance estimée."""
    src_raw = m.all_sources[0]      if m.all_sources      else None
    dst_raw = m.all_destinations[0] if m.all_destinations else None
    src = resolved.get(src_raw) if src_raw else None
    dst = resolved.get(dst_raw) if dst_raw else None
    d1 = dist.get((start_node, src), _UNKNOWN_DIST_PENALTY) if (start_node and src) else _UNKNOWN_DIST_PENALTY
    d2 = dist.get((src, dst),        _UNKNOWN_DIST_PENALTY) if (src and dst)        else _UNKNOWN_DIST_PENALTY
    return float(m.reward_uec) / max(1.0, d1 + d2)


def _select_best_subset(
    criterion: str,
    missions: list,
    start_node: str | None,
    resolved: dict,
    dist: dict,
    max_size: int = 5,
    progress_cb=None,    # callable(done: int, total: int) ou None
    cancel_event=None,   # threading.Event ou None
) -> tuple[list, float]:
    """Sélectionne le sous-ensemble de 2..max_size missions qui maximise le critère.

    Stratégie (Option C) :
      - Si n > _PREFILTER_THRESHOLD : pré-filtre les _PREFILTER_KEEP meilleures
        missions (score individuel reward/distance) avant le brute-force.
      - Sinon : brute-force exact sur toutes les missions.
      - Pour chaque combinaison, calcule le tour optimal (TSP exhaustif ≤ 7 missions).

    Scores :
      dist    → minimise la distance totale du tour
      benef   → maximise la récompense totale, avec pénalité si >80 Gm/mission en moyenne
      roi     → maximise récompense / distance

    Retourne (liste d'indices dans missions ORIGINALE dans l'ordre optimal, distance totale).
    """
    from itertools import combinations as _combos
    from math import comb as _comb

    n = len(missions)

    # ── Pré-filtrage si trop de missions ─────────────────────────────────────
    original_indices = list(range(n))
    if n > _PREFILTER_THRESHOLD:
        scores = [_prefilter_score(missions[i], start_node, resolved, dist) for i in range(n)]
        ranked = sorted(range(n), key=lambda i: scores[i], reverse=True)
        keep   = ranked[:_PREFILTER_KEEP]
        missions = [missions[i] for i in keep]
        original_indices = keep
        n = len(missions)

    max_k = min(max_size, n)
    min_k = min(2, n)

    # Pénalité "benef" : au-delà de 80 Gm/mission la récompense est réduite
    BENEF_GM_BUDGET = 80.0

    best_score: float = -float("inf")
    best_indices: list[int] = list(range(min_k))
    best_dist: float = float("inf")

    total_combos = sum(_comb(n, k) for k in range(min_k, max_k + 1))
    done_combos  = 0
    _PROG_STEP   = max(1, total_combos // 40)   # mise à jour toutes les ~2.5%

    class _Cancelled(Exception):
        pass

    try:
        for k in range(min_k, max_k + 1):
            for combo in _combos(range(n), k):
                done_combos += 1
                if done_combos % _PROG_STEP == 0:
                    if cancel_event and cancel_event.is_set():
                        raise _Cancelled
                    if progress_cb:
                        progress_cb(done_combos, total_combos)

                sub = [missions[i] for i in combo]
                local_order, tour_d = _tsp_brute_force(start_node, sub, resolved, dist)
                total_rew = sum(sub[j].reward_uec for j in local_order)

                # Exclure les combinaisons avec distances entièrement inconnues
                has_real_dist = tour_d < _UNKNOWN_DIST_PENALTY * k

                if criterion in ("dist", "distance", "court"):
                    score = -tour_d if has_real_dist else -1e12
                elif criterion in ("benefice", "bénéfice", "benef", "bénef"):
                    avg_gm = (tour_d / k) if k > 0 and has_real_dist else float("inf")
                    excess = max(0.0, avg_gm - BENEF_GM_BUDGET)
                    score = float(total_rew) - excess * 800
                elif criterion == "roi":
                    score = (total_rew / tour_d) if tour_d > 0 and has_real_dist else -1e12
                else:
                    score = 0.0

                if score > best_score:
                    best_score = score
                    best_indices = [combo[j] for j in local_order]
                    best_dist = tour_d
    except _Cancelled:
        pass  # retourner le meilleur résultat partiel

    # Remappe vers les indices originaux si pré-filtrage appliqué
    remapped = [original_indices[i] for i in best_indices]
    return remapped, best_dist


def _progress(msg: str, use_tty: bool) -> None:
    """Affiche une ligne de progression (remplaçable si tty)."""
    if use_tty:
        sys.stdout.write(f"\r  {msg}   ")
        sys.stdout.flush()
    else:
        console.print(f"  [{C.DIM}]{msg}[/{C.DIM}]")


def _progress_done(use_tty: bool) -> None:
    """Termine la ligne de progression courante."""
    if use_tty:
        sys.stdout.write("\r\033[K")  # efface la ligne
        sys.stdout.flush()


def _show_calc_help(ctx=None) -> None:
    section("Aide — /voyage calc")
    console.print(
        f"  [{C.LABEL}]Critères :[/{C.LABEL}]\n"
        f"    [bold]dist[/bold]      Minimise la distance totale du voyage\n"
        f"    [bold]benef[/bold]     Maximise la récompense totale\n"
        f"    [bold]roi[/bold]       Maximise le ROI (aUEC/Gm)\n"
        f"    [bold]all[/bold]       Génère les 3 propositions simultanément\n"
    )
    console.print(
        f"  [{C.LABEL}]Options :[/{C.LABEL}]\n"
        f"    [bold]--max[/bold]:[italic]N[/italic]             Nb max de missions par voyage\n"
        f"    [bold]--boucle[/bold] / [bold]--blc[/bold]   Inclure le retour au départ\n"
        f"    [bold]--station[/bold]           Lieux stations uniquement\n"
        f"    [bold]--ship[/bold]:[italic]nom[/italic]         Vaisseau spécifique (filtre SCU)\n"
        f"    [bold]--to[/bold] [italic]lieu[/italic]          Passer par ce lieu obligatoirement\n"
        f"    [bold]--exclude[/bold] [italic]lieu[/italic]     Exclure ce lieu (s'ajoute à voyage.calc.exclure)\n"
        f"    [bold]--com[/bold]               [{C.DIM}]bientôt[/{C.DIM}] Suggérer du commerce pour les gaps\n"
    )
    console.print(
        f"  [{C.LABEL}]Config voyage.calc :[/{C.LABEL}]\n"
        f"    [bold]/config voyage.calc.nbsaut[/bold] [italic]N[/italic]      Nb max missions (défaut 5)\n"
        f"    [bold]/config voyage.calc.prop[/bold] [italic]N[/italic]         1=critère seul · ≥2=dist+benef+roi\n"
        f"    [bold]/config voyage.calc.options[/bold] [italic]\"…\"[/italic]   Options injectées automatiquement\n"
        f"    [bold]/config voyage.calc.gap_max[/bold] [italic]N[/italic]      Transit ⚠ au-delà de N Gm (défaut 3)\n"
        f"    [bold]/config voyage.calc.favoris[/bold] [italic][…][/italic]    Lieux à privilégier\n"
        f"    [bold]/config voyage.calc.exclure[/bold] [italic][…][/italic]    Lieux à exclure systématiquement\n"
    )
    # Rappel valeurs actuelles si ctx fourni
    if ctx is not None:
        vcalc = ctx.cfg.get("voyage", {}).get("calc", {})
        fav   = vcalc.get("favoris", [])
        excl  = vcalc.get("exclure", [])
        console.print(
            f"  [{C.LABEL}]Valeurs actuelles :[/{C.LABEL}]\n"
            f"    nbsaut=[bold]{vcalc.get('nbsaut', 5)}[/bold]  "
            f"prop=[bold]{vcalc.get('prop', 1)}[/bold]  "
            f"gap_max=[bold]{vcalc.get('gap_max', 3.0)}Gm[/bold]\n"
            f"    options=[bold]{vcalc.get('options', '') or '(aucune)'}[/bold]\n"
            f"    favoris=[bold]{', '.join(fav) if fav else '(aucun)'}[/bold]\n"
            f"    exclure=[bold]{', '.join(excl) if excl else '(aucun)'}[/bold]\n"
        )
    console.print(
        f"  [{C.DIM}]Exemples :[/{C.DIM}]\n"
        f"    [{C.DIM}]/voyage calc roi --boucle --station[/{C.DIM}]\n"
        f"    [{C.DIM}]/voyage calc all --ship:Cutlass_Black[/{C.DIM}]\n"
        f"    [{C.DIM}]/voyage calc benef --to ArcCorp --exclude microTech[/{C.DIM}]\n"
        f"\n"
        f"  [{C.DIM}]Après affichage :[/{C.DIM}]\n"
        f"    [{C.DIM}][bold]+N[/bold]      Ajouter la proposition N au voyage actif[/{C.DIM}]\n"
        f"    [{C.DIM}][bold]+nN[/bold]     Créer un nouveau voyage avec la proposition N[/{C.DIM}]\n"
        f"    [{C.DIM}][bold]+mID[/bold]    Ajouter uniquement la mission #ID au voyage actif[/{C.DIM}]\n"
    )


def _resolve_ship_scu(ship_name: str | None, ctx) -> int | None:
    """Retourne la capacité SCU du vaisseau nommé, ou None si introuvable."""
    if ship_name:
        name_lower = ship_name.lower().replace("_", " ")
        for v in ctx.cache.vehicles:
            if (getattr(v, "name", "").lower() == name_lower
                    or getattr(v, "name_full", "").lower() == name_lower):
                return v.scu or 0
        player = getattr(ctx, "player", None)
        if player:
            for s in (player.ships or []):
                if s.name.lower() == name_lower:
                    return s.scu or 0
        print_warn(f"Vaisseau '{ship_name}' introuvable — filtre SCU ignoré")
        return None
    ship = _active_ship(getattr(ctx, "player", None))
    return ship.scu if ship else None


def _cmd_new_auto(criterion: str, raw_args: list[str], ctx) -> None:
    """Génère un ou plusieurs voyages optimisés et les affiche pour sélection."""
    mm = ctx.mission_manager
    vm = ctx.voyage_manager
    graph = ctx.cache.transport_graph

    # ── Lecture config voyage.calc ────────────────────────────────────────────
    vcalc    = ctx.cfg.get("voyage", {}).get("calc", {})
    cfg_max  = int(vcalc.get("nbsaut", 5))
    cfg_prop = int(vcalc.get("prop",   1))
    cfg_opts = str(vcalc.get("options", "")).split()
    cfg_fav  = list(vcalc.get("favoris", []))
    cfg_excl = list(vcalc.get("exclure", []))
    cfg_gap  = float(vcalc.get("gap_max", _GAP_WARN_GM))

    # Fusionner options config + CLI (CLI a priorité)
    merged_args = cfg_opts + list(raw_args)
    opts = _parse_auto_opts(merged_args)
    if "max_missions" not in raw_args and "--max" not in " ".join(raw_args):
        opts["max_missions"] = cfg_max
    # Injecter exclusions config (s'ajoutent aux exclusions CLI)
    opts["exclude"] = list(set(opts["exclude"]) | {e.lower() for e in cfg_excl})

    # Critères à générer
    is_all = criterion in ("all", "tous") or cfg_prop >= 2
    criteria = _SINGLE_CRITERIA if is_all else [criterion]

    section("Voyage calc — " + _AUTO_CRITERIA.get(criterion, criterion))

    # ── Rappel des paramètres utilisés ───────────────────────────────────────
    recap_parts = [f"max [bold]{opts['max_missions']}[/bold] missions"]
    if opts["boucle"]:
        recap_parts.append("boucle ↺")
    if opts["station"]:
        recap_parts.append("stations uniquement")
    if opts["exclude"]:
        recap_parts.append(f"exclus : {', '.join(opts['exclude'][:3])}")
    if cfg_fav:
        recap_parts.append(f"favoris : {', '.join(cfg_fav[:3])}")
    if opts["to"]:
        recap_parts.append(f"via : {', '.join(opts['to'])}")
    console.print(f"  [{C.DIM}]{' · '.join(recap_parts)}[/{C.DIM}]")

    missions = list(mm.missions)
    if not missions:
        print_warn("Catalogue vide — /mission add pour créer des missions")
        return

    # ── Filtre vaisseau ───────────────────────────────────────────────────────
    ship_scu = _resolve_ship_scu(opts.get("ship"), ctx)
    if ship_scu is not None:
        too_big = [m for m in missions if m.total_scu > ship_scu and m.total_scu > 0]
        if too_big:
            console.print(
                f"  [{C.WARNING}]{len(too_big)} mission(s) exclue(s) "
                f"(SCU > {ship_scu})[/{C.WARNING}]"
            )
        missions = [m for m in missions if m.total_scu <= ship_scu or m.total_scu == 0]
        if not missions:
            print_warn("Aucune mission compatible avec la capacité du vaisseau")
            return

    # ── Filtre station ────────────────────────────────────────────────────────
    if opts["station"]:
        missions = [
            m for m in missions
            if all(_loc_is_station(l) for l in m.all_sources + m.all_destinations)
        ]
        if not missions:
            print_warn("Aucune mission entre stations uniquement")
            return

    # ── Filtre exclusions ─────────────────────────────────────────────────────
    excl = [e.lower() for e in opts["exclude"]]
    if excl:
        missions = [
            m for m in missions
            if not any(
                any(e in loc.lower() for e in excl)
                for loc in m.all_sources + m.all_destinations
            )
        ]
        if not missions:
            print_warn("Aucune mission après exclusion des lieux")
            return

    # ── Filtre --to ───────────────────────────────────────────────────────────
    to_locs = [t.lower() for t in opts["to"]]
    if to_locs:
        def _touches_to(m) -> bool:
            return any(
                any(t in loc.lower() for t in to_locs)
                for loc in m.all_sources + m.all_destinations
            )
        must_have = [m for m in missions if _touches_to(m)]
        others    = [m for m in missions if not _touches_to(m)]
        missions  = must_have + others
        if not must_have:
            print_warn(
                f"Aucune mission ne passe par : {', '.join(opts['to'])}\n"
                f"  [{C.DIM}]Le filtre --to est ignoré[/{C.DIM}]"
            )

    # ── Filtre reward=0 pour critère ROI ─────────────────────────────────────
    if criterion == "roi":
        no_reward = [m for m in missions if m.reward_uec == 0]
        if no_reward:
            console.print(
                f"  [{C.WARNING}]{len(no_reward)} mission(s) sans récompense ignorée(s) "
                f"(OCR incomplet)[/{C.WARNING}]"
            )
        missions = [m for m in missions if m.reward_uec > 0]
        if not missions:
            print_warn("Aucune mission avec récompense connue — relancez /mission scan")
            return

    # ── Stubs futurs ──────────────────────────────────────────────────────────
    if opts.get("com"):
        console.print(
            f"  [{C.WARNING}]--com : complétion commerciale non encore implémentée[/{C.WARNING}]"
        )
    if opts.get("favoris"):
        console.print(
            f"  [{C.WARNING}]--favoris : filtrage favoris non encore implémenté[/{C.WARNING}]"
        )

    # ── Collecte des lieux ────────────────────────────────────────────────────
    start_raw = _player_loc(ctx) or ""
    all_locs: list[str] = []
    if start_raw:
        all_locs.append(start_raw)
    for m in missions:
        for loc in m.all_sources + m.all_destinations:
            if loc and loc not in all_locs:
                all_locs.append(loc)

    in_overlay = getattr(ctx, "_overlay_send_fn", None) is not None
    use_tty    = not in_overlay and hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    # ── Résolution des lieux ─────────────────────────────────────────────────
    _progress(f"Résolution {len(all_locs)} lieux, {len(missions)} mission(s)…", use_tty)
    resolved = _resolve_locs(all_locs, graph) if graph else {}

    missing = [l for l in all_locs if not resolved.get(l)]
    _progress_done(use_tty)
    if missing:
        console.print(
            f"  [{C.WARNING}]{len(missing)} lieu(x) non résolu(s) : "
            f"{', '.join(missing[:5])}{'…' if len(missing) > 5 else ''}[/{C.WARNING}]"
        )

    node_list = list(dict.fromkeys(v for v in resolved.values() if v))
    n_nodes   = len(node_list)

    # ── Matrice de distances avec progression ────────────────────────────────
    _progress(f"Matrice {n_nodes}×{n_nodes}…", use_tty)
    dist: dict = {}
    for i, a in enumerate(node_list):
        for b in node_list:
            if (b, a) in dist:
                dist[(a, b)] = dist[(b, a)]
            elif a == b:
                dist[(a, b)] = 0.0
            else:
                dist[(a, b)] = _path_dist(graph, a, b)
        if use_tty and n_nodes > 5:
            pct = int((i + 1) / n_nodes * 100)
            sys.stdout.write(f"\r  Matrice {n_nodes}×{n_nodes}… {pct}%   ")
            sys.stdout.flush()
    _progress_done(use_tty)

    start_node = resolved.get(start_raw) if start_raw else None
    if not start_node and missions and missions[0].all_sources:
        start_node = resolved.get(missions[0].all_sources[0])

    # ── Génération des propositions ───────────────────────────────────────────
    proposals: list[dict] = []
    max_missions = opts["max_missions"]

    from math import comb as _comb
    n = len(missions)
    n_eff = min(n, _PREFILTER_KEEP) if n > _PREFILTER_THRESHOLD else n
    n_combos = sum(
        _comb(n_eff, k)
        for k in range(min(2, n_eff), min(max_missions, n_eff) + 1)
    )
    pre_note = f" (pré-filtre top-{n_eff}/{n})" if n > _PREFILTER_THRESHOLD else ""
    _progress(
        f"Test {n_combos:,} combinaisons (≤{max_missions} missions{pre_note})…",
        use_tty,
    )
    if not use_tty:
        console.print(f"  [{C.DIM}]Calcul en cours…[/{C.DIM}]")

    for crit in criteria:
        crit_label = _AUTO_CRITERIA.get(crit, crit)

        # Callback de progression
        _last_pct = [-1]
        def _prog_cb(done: int, total: int, label: str = crit_label) -> None:
            pct = int(done / total * 100)
            if pct == _last_pct[0]:
                return
            _last_pct[0] = pct
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            if use_tty:
                sys.stdout.write(f"\r  [{label}] {bar} {pct}%  ({done:,}/{total:,})   ")
                sys.stdout.flush()
            elif in_overlay:
                pfn = getattr(ctx, "_overlay_progress_fn", None)
                if pfn:
                    pfn(pct, label, done, total)
            else:
                console.print(f"  [{C.DIM}][{label}] {bar} {pct}%[/{C.DIM}]")

        indices, _approx_dist = _select_best_subset(
            crit, missions, start_node, resolved, dist,
            max_size=max_missions, progress_cb=_prog_cb,
            cancel_event=getattr(ctx, "_cancel_flag", None),
        )
        selected = [missions[i] for i in indices]

        # ── Route réelle multi-arrêt (remplace l'approximation TSP) ──────────
        ship_scu = float("inf")
        _player = ctx.player if ctx else None
        _ship   = _active_ship(_player)
        if _ship and _ship.scu:
            ship_scu = float(_ship.scu)

        ordered_nodes, tour_dist, route_nodes = _route_solve(
            start_node, selected, resolved, dist, ship_scu
        )
        route = _route_detail(
            ordered_nodes, route_nodes, selected, dist, start_node, ship_scu
        )

        # --boucle : ajouter le retour au départ
        if opts["boucle"] and start_node and ordered_nodes:
            ret_d = dist.get((ordered_nodes[-1], start_node))
            if ret_d is not None:
                tour_dist += ret_d

        total_rew = sum(m.reward_uec for m in selected)
        roi = total_rew / tour_dist if tour_dist > 0 else 0.0

        # Estimation temps de chargement (8 SCU/trip × 25s, arrondi au min)
        import math as _math
        load_secs = sum(
            _math.ceil((m.total_scu or 0) / 8) * 25
            for m in selected if m.total_scu
        )
        load_min = round(load_secs / 60)

        proposals.append({
            "criterion": crit,
            "label":     crit_label,
            "algo":      f"{len(selected)} missions / {len(missions)} dispo",
            "dist":      tour_dist,
            "reward":    total_rew,
            "load_min":  load_min,
            "roi":       roi,
            "missions":  selected,
            "route":     route,          # stops ordonnés avec détail cargo
            "ship_scu":  ship_scu,
            "loop":      opts["boucle"],
        })

    _progress_done(use_tty)

    # ── Affichage des propositions ────────────────────────────────────────────
    active_voyage = vm.get_active()
    console.print()
    for p_idx, prop in enumerate(proposals, 1):
        rew_s  = f"{prop['reward']:,}".replace(",", " ")
        roi_s  = f"{prop['roi']:,.0f}".replace(",", " ")
        boucle = "  [boucle ↺]" if prop["loop"] else ""
        dist_ok = prop["dist"] < _UNKNOWN_DIST_PENALTY * len(prop["missions"])
        dist_s  = _fmt_dist(prop["dist"]) if dist_ok else "? (dist. inconnues)"
        load_s = f"  ·  Charg. ≈ {prop['load_min']} min" if prop.get('load_min') else ""
        section(f"P{p_idx} — {prop['label']}  [{prop['algo']}]")
        console.print(
            f"  Dist : [bold]{dist_s}[/bold]{boucle}  ·  "
            f"Récompense : [bold]{rew_s} aUEC[/bold]  ·  "
            f"ROI : [bold]{roi_s} aUEC/Gm[/bold]{load_s}"
        )
        console.print()

        # ── Table par arrêt (route multi-stop) ───────────────────────────────
        tbl = adaptive_table([
            ColSpec("Ét.",     width=3,   justify="right", style=C.DIM),
            ColSpec("Arrêt",   flex=1,    min_flex=12,     style=C.UEX),
            ColSpec("Transit", width=9,   justify="right"),
            ColSpec("Action",  flex=2,    min_flex=20),
            ColSpec("Soute",   width=9,   justify="right"),
        ])

        _ship_s = f"/{prop['ship_scu']:.0f}" if prop["ship_scu"] < float("inf") else ""
        for step_idx, stop in enumerate(prop.get("route", []), 1):
            transit_d = stop["transit_gm"]
            transit_s = _fmt_dist(transit_d) if transit_d is not None else "—"
            if transit_d is not None and transit_d > cfg_gap:
                transit_s = f"[{C.WARNING}]{transit_s} ⚠[/{C.WARNING}]"

            # Construire la description de l'action à cet arrêt
            action_parts = []
            for a in stop["delivers"]:
                comm_s = f" {a['commodity']}" if a["commodity"] else ""
                scu_s  = f" {a['scu']:.0f} SCU" if a["scu"] else ""
                action_parts.append(f"[{C.LOSS}]▼ LIVRER{scu_s}{comm_s}[/{C.LOSS}]")
            for a in stop["pickups"]:
                comm_s = f" {a['commodity']}" if a["commodity"] else ""
                scu_s  = f" {a['scu']:.0f} SCU" if a["scu"] else ""
                action_parts.append(f"[{C.PROFIT}]▲ CHARGER{scu_s}{comm_s}[/{C.PROFIT}]")

            action_s = "  ".join(action_parts) or f"[{C.DIM}]transit[/{C.DIM}]"
            cargo_s  = f"{stop['cargo_after']:.0f} SCU{_ship_s}"
            if prop["ship_scu"] < float("inf") and stop["cargo_after"] > prop["ship_scu"]:
                cargo_s = f"[{C.LOSS}]{cargo_s} ⚠[/{C.LOSS}]"

            # Ordre de chargement LIFO si plusieurs cargos à charger
            lo = stop.get("loading_order", [])
            if len(lo) > 1:
                lo_parts = [f"{i+1}. {a['scu']:.0f} SCU {a['commodity']} " for i, a in enumerate(lo)]
                lo_hint  = f" [{C.DIM}](ordre fond→porte : {' | '.join(lo_parts)})[/{C.DIM}]"
                action_s += lo_hint

            tbl.add_row(str(step_idx), stop["raw"], transit_s, action_s, cargo_s)

        console.print(tbl)

        # Missions dans ce trajet (rappel)
        mission_ids = ", ".join(f"#{m.id}" for m in prop["missions"])
        console.print(f"  [{C.DIM}]Missions : {mission_ids}[/{C.DIM}]")

        if not in_overlay:
            # Missions individuelles avec bouton + (CLI seulement)
            console.print(f"  [{C.DIM}]Missions : ", end="")
            for m in prop["missions"]:
                console.print(f"[bold]+m{m.id}[/bold] #{m.id} ", end="")
            console.print(f"[/{C.DIM}]")

            # Boutons proposition (CLI seulement)
            if active_voyage:
                console.print(
                    f"  [{C.DIM}][bold]+{p_idx}[/bold] → ajouter au voyage «[/{C.DIM}]"
                    f"[{C.LABEL}]{active_voyage.name}[/{C.LABEL}]"
                    f"[{C.DIM}]»  [bold]+n{p_idx}[/bold] → nouveau voyage[/{C.DIM}]"
                )
            else:
                console.print(
                    f"  [{C.DIM}][bold]+{p_idx}[/bold] → nouveau voyage  "
                    f"[bold]/voyage on[/bold] pour activer un voyage d'abord[/{C.DIM}]"
                )
            console.print()

    # ── Sauvegarder une proposition ───────────────────────────────────────────
    ctx._last_calc_proposals = proposals  # accessible via /voyage + N

    if in_overlay:
        send_fn = ctx._overlay_send_fn

        # Résoudre les chemins de screenshots
        try:
            from uexinfo.cache.screenshot_db import ScreenshotDB as _SDB
            import re as _re
            _sdb = getattr(ctx, "screenshot_db", None) or _SDB()
        except Exception:
            _sdb = None

        def _screenshot_path(m) -> str | None:
            if not _sdb or not m.source_raw or not m.source_raw.startswith("ocr:"):
                return None
            filename = m.source_raw[4:]
            try:
                entry = _sdb.get(filename)
                return entry.path if entry and entry.path else None
            except Exception:
                return None

        def _prop_scu(missions) -> tuple[int, int]:
            """(scu_min, scu_max) pour une proposition."""
            known = [m.total_scu for m in missions if m.total_scu]
            if not known:
                return 0, 0
            total = sum(known)
            # Si certaines missions ont SCU=0/inconnu → min = connu, max = connu (on indique ?)
            has_unknown = any(not m.total_scu for m in missions)
            return total, total  # simplifié : afficher ? si has_unknown

        send_fn({
            "type":          "voyage_calc_result",
            "proposals":     [
                {
                    "idx":     p_idx,
                    "label":   p["label"],
                    "dist":    _fmt_dist(p["dist"]) if p["dist"] < _UNKNOWN_DIST_PENALTY * len(p["missions"]) else "?",
                    "reward":  p["reward"],
                    "roi":     round(p["roi"], 0),
                    "loop":    p["loop"],
                    "scu_total":   sum(m.total_scu or 0 for m in p["missions"]),
                    "scu_unknown": any(not m.total_scu for m in p["missions"]),
                    "load_min":    p.get("load_min", 0),
                    "missions": [
                        {
                            "id":              m.id,
                            "name":            m.name or "",
                            "src":             m.all_sources[0]      if m.all_sources      else "",
                            "dst":             m.all_destinations[0] if m.all_destinations else "",
                            "reward":          m.reward_uec,
                            "scu":             m.total_scu or 0,
                            "screenshot_path": _screenshot_path(m),
                        }
                        for m in p["missions"]
                    ],
                    "route": [
                        {
                            "raw":        s["raw"],
                            "transit_gm": round(s["transit_gm"], 1) if s["transit_gm"] is not None else None,
                            "delivers":   s["delivers"],
                            "pickups":    s["pickups"],
                            "cargo":      round(s["cargo_after"], 1),
                            "loading_order": s.get("loading_order", []),
                        }
                        for s in p.get("route", [])
                    ],
                    "ship_scu": p.get("ship_scu", 0),
                }
                for p_idx, p in enumerate(proposals, 1)
            ],
            "active_voyage": active_voyage.name if active_voyage else None,
        })
        console.print(
            f"[{C.DIM}]Tapez [bold]/voyage + <N>[/bold] pour sauvegarder "
            f"(ex : [bold]/voyage + 1[/bold])  ·  "
            f"[bold]+mN[/bold] pour ajouter une mission seule[/{C.DIM}]"
        )
    else:
        console.print(
            f"[{C.DIM}]+<N> sauvegarder · +n<N> nouveau voyage · "
            f"+m<ID> ajouter mission · Entrée annuler : [/{C.DIM}]",
            end="",
        )
        try:
            raw = input().strip()
        except (EOFError, KeyboardInterrupt):
            return
        if raw:
            _handle_save_input(raw, proposals, ctx)


def _cmd_save_proposal(rest: list[str], ctx) -> None:
    """Sauvegarde la proposition N du dernier /voyage calc."""
    proposals = getattr(ctx, "_last_calc_proposals", None)
    if not proposals:
        print_warn(
            "Aucune proposition disponible — lancez /voyage calc <critère> d'abord"
        )
        return
    ref = (rest[0] if rest else "1").lstrip("+")
    force_new = ref.lower().startswith("n")
    if force_new:
        ref = ref[1:]
    try:
        idx = int(ref) - 1
    except ValueError:
        print_error("Usage : /voyage + <N>  ou  /voyage + n<N> (nouveau voyage)  (ex: /voyage + 1)")
        return
    if not 0 <= idx < len(proposals):
        print_error(f"Proposition {idx + 1} inexistante (1–{len(proposals)})")
        return
    _save_proposal_by_index(idx, proposals, ctx, force_new=force_new)


def _handle_save_input(raw: str, proposals: list, ctx) -> None:
    mm = ctx.mission_manager
    vm = ctx.voyage_manager
    for ref in raw.split(","):
        ref = ref.strip().lstrip("+").strip()
        if not ref:
            continue
        # +mN → ajouter mission #N au voyage actif
        if ref.lower().startswith("m"):
            try:
                mid = int(ref[1:])
            except ValueError:
                print_warn(f"Référence mission invalide : +m{ref[1:]}")
                continue
            m = mm.get(str(mid))
            if not m:
                print_warn(f"Mission #{mid} introuvable")
                continue
            active = vm.get_active()
            if not active:
                print_warn("Aucun voyage actif — /voyage on d'abord")
                continue
            vm.add_missions(active, [m.id])
            print_ok(f"Mission #{m.id} ajoutée au voyage «{active.name}»")
            continue
        # +nN → sauvegarder P{N} dans un nouveau voyage (forcer nouveau)
        force_new = ref.lower().startswith("n")
        if force_new:
            ref = ref[1:]
        try:
            idx = int(ref) - 1
        except ValueError:
            print_warn(f"Référence invalide : {ref!r}")
            continue
        if 0 <= idx < len(proposals):
            _save_proposal_by_index(idx, proposals, ctx, force_new=force_new)
        else:
            print_warn(f"Proposition {idx + 1} inexistante")


def _save_proposal_by_index(idx: int, proposals: list, ctx, force_new: bool = False) -> None:
    vm        = ctx.voyage_manager
    prop      = proposals[idx]
    mission_ids = [prop["missions"][i].id for i in prop["order"]]
    rew_s     = f"{prop['reward']:,}".replace(",", " ")
    start_raw = _player_loc(ctx) or None

    active = vm.get_active()
    if active and not force_new:
        # Ajouter au voyage actif
        vm.add_missions(active, mission_ids)
        vm.update(active)
        print_ok(
            f"P{idx + 1} → ajouté au voyage [{C.UEX}]{active.name}[/{C.UEX}]  #{active.id} : "
            f"{len(mission_ids)} mission(s) · {_fmt_dist(prop['dist'])} · {rew_s} aUEC"
        )
    else:
        # Créer un nouveau voyage
        v = vm.new_voyage(name=f"calc-{prop['criterion']}", departure=start_raw)
        v.loop = prop.get("loop", False)
        vm.add_missions(v, mission_ids)
        vm.update(v)
        print_ok(
            f"P{idx + 1} → nouveau voyage [{C.UEX}]{v.name}[/{C.UEX}]  #{v.id} créé : "
            f"{len(mission_ids)} mission(s) · {_fmt_dist(prop['dist'])} · {rew_s} aUEC"
        )
        console.print(f"  [{C.DIM}]/voyage accept  pour analyser et démarrer[/{C.DIM}]")


# ── Analyse TSP + distances ───────────────────────────────────────────────────

def _fmt_dist(d: float | None) -> str:
    if d is None:
        return "?"
    return f"{d:.1f}Gm" if d >= 1 else f"{d*1000:.0f}Mm"


def _path_dist(graph, a: str | None, b: str | None) -> float | None:
    """Distance entre deux nœuds résolus (None si injoignable)."""
    if not a or not b:
        return None
    if a == b:
        return 0.0
    try:
        r = graph.find_shortest_path(a, b)
        return r.total_distance if r is not None else None
    except Exception:
        return None


def _resolve_locs(raw_locs: list[str], graph) -> dict[str, str | None]:
    """Résout une liste de noms bruts en nœuds du graphe (fuzzy)."""
    from uexinfo.cache.mission_scan import _resolve_graph_node
    resolved: dict[str, str | None] = {}
    # Premier passage : résoudre les non-gateways pour dériver le system_hint
    from uexinfo.cache.mission_scan import _node_system
    system_counts: dict[str, int] = {}
    for loc in raw_locs:
        node = _resolve_graph_node(loc, graph)
        resolved[loc] = node
        if node and "gateway" not in (node or "").lower():
            sys = _node_system(node, graph)
            if sys:
                system_counts[sys] = system_counts.get(sys, 0) + 1
    system_hint = max(system_counts, key=system_counts.__getitem__) if system_counts else None
    # Second passage : gateways avec system_hint
    for loc in raw_locs:
        if resolved[loc] and "gateway" in resolved[loc].lower():
            resolved[loc] = _resolve_graph_node(loc, graph, system_hint=system_hint)
    return resolved


def _build_dist_matrix(
    graph,
    nodes: list[str | None],
) -> dict[tuple[str | None, str | None], float | None]:
    """Calcule toutes les distances pairwise entre les nœuds résolus."""
    matrix: dict[tuple[str | None, str | None], float | None] = {}
    for a in nodes:
        for b in nodes:
            if (a, b) in matrix:
                continue
            if a == b:
                matrix[(a, b)] = 0.0
            elif (b, a) in matrix:
                matrix[(a, b)] = matrix[(b, a)]
            else:
                matrix[(a, b)] = _path_dist(graph, a, b)
    return matrix


def _tsp_nearest_neighbor(
    start_node: str | None,
    missions: list,
    resolved: dict[str, str | None],
    dist: dict,
) -> tuple[list, float]:
    """Heuristique du plus proche voisin."""
    remaining = list(range(len(missions)))
    order: list[int] = []
    cur = start_node
    total = 0.0

    while remaining:
        best_i = None
        best_d = float("inf")
        for i in remaining:
            m = missions[i]
            src_raw = m.all_sources[0] if m.all_sources else None
            src = resolved.get(src_raw) if src_raw else None
            d = dist.get((cur, src))
            if d is None:
                d = float("inf")
            if d < best_d:
                best_d = d
                best_i = i
        if best_i is None:
            best_i = remaining[0]
            best_d = 0.0
        order.append(best_i)
        remaining.remove(best_i)
        m = missions[best_i]
        src_raw = m.all_sources[0] if m.all_sources else None
        dst_raw = m.all_destinations[0] if m.all_destinations else None
        src = resolved.get(src_raw) if src_raw else None
        dst = resolved.get(dst_raw) if dst_raw else None
        total += best_d
        d_inner = dist.get((src, dst))
        total += d_inner if d_inner is not None else 0.0
        cur = dst or src
    return order, total


def _dist_val(dist: dict, a, b) -> float:
    """Distance entre nœuds a et b.
    Retourne _UNKNOWN_DIST_PENALTY si la distance est None/inconnue,
    jamais 0 pour des nœuds différents (évite de traiter l'inconnu comme gratuit).
    """
    if not a or not b:
        return _UNKNOWN_DIST_PENALTY
    if a == b:
        return 0.0
    d = dist.get((a, b))
    return d if d is not None else _UNKNOWN_DIST_PENALTY


def _tsp_brute_force(
    start_node: str | None,
    missions: list,
    resolved: dict[str, str | None],
    dist: dict,
) -> tuple[list, float]:
    """Parcours exhaustif (≤8 missions)."""
    import itertools
    best_order = list(range(len(missions)))
    best_total = float("inf")

    for perm in itertools.permutations(range(len(missions))):
        total = 0.0
        cur = start_node
        prev_dst = start_node
        for step, i in enumerate(perm):
            m = missions[i]
            src_raw = m.all_sources[0] if m.all_sources else None
            dst_raw = m.all_destinations[0] if m.all_destinations else None
            src = resolved.get(src_raw) if src_raw else None
            dst = resolved.get(dst_raw) if dst_raw else None
            # Transit vers la source de cette mission
            transit = _dist_val(dist, cur, src) if src else 0.0
            total += transit
            # Bonus si enchaînement direct (destination précédente == source)
            if step > 0 and prev_dst and src and prev_dst == src:
                total -= _CHAIN_BONUS_GM
            if src:
                cur = src
            # Leg de la mission (source → destination)
            total += _dist_val(dist, cur, dst) if dst else 0.0
            if dst:
                prev_dst = dst
                cur = dst
        if total < best_total:
            best_total = total
            best_order = list(perm)

    return best_order, best_total


# ── Modèle route multi-arrêt (Pickup and Delivery) ───────────────────────────

def _build_route_nodes(missions: list, resolved: dict) -> dict:
    """
    Construit la carte des nœuds d'arrêt à partir des objectifs de missions.

    Retourne un dict { node_str → {"raw": str, "pickups": [...], "delivers": [...]} }
    où chaque action est { "mi": int, "commodity": str, "scu": float }.

    Si plusieurs missions ont un pickup au même nœud → fusionné en un seul arrêt.
    Si mission A livre au nœud X et mission B charge au nœud X → même arrêt (chaîne).
    """
    nodes: dict[str, dict] = {}

    def _node_for(raw: str | None) -> str | None:
        if not raw:
            return None
        return resolved.get(raw)

    for mi, m in enumerate(missions):
        for obj in m.objectives:
            src_node = _node_for(obj.source)
            dst_node = _node_for(obj.destination)
            comm     = obj.commodity or ""
            scu      = float(obj.quantity_scu or 0)
            action   = {"mi": mi, "commodity": comm, "scu": scu}

            if src_node:
                if src_node not in nodes:
                    nodes[src_node] = {"raw": obj.source, "pickups": [], "delivers": []}
                nodes[src_node]["pickups"].append(action)

            if dst_node:
                if dst_node not in nodes:
                    nodes[dst_node] = {"raw": obj.destination, "pickups": [], "delivers": []}
                nodes[dst_node]["delivers"].append(action)

    return nodes


def _route_solve(
    start_node: str | None,
    missions:   list,
    resolved:   dict,
    dist:       dict,
    ship_scu:   float = float("inf"),
) -> tuple[list[str], float, dict]:
    """
    Trouve l'ordre optimal des arrêts pour un ensemble de missions.

    Contraintes :
      • Pour chaque objectif (src→dst), le nœud source doit être visité AVANT
        le nœud destination.
      • À tout moment, cargo cumulé ≤ ship_scu.

    Stratégie :
      • ≤ 10 arrêts uniques → backtracking exhaustif avec élagage
      • > 10 arrêts        → plus proche voisin contraint

    Retourne (ordered_nodes, total_dist, nodes_dict).
    """
    nodes = _build_route_nodes(missions, resolved)
    if not nodes:
        return [], 0.0, nodes

    # ── Précédences : dst_node peut être visité seulement après src_node ─────
    prereqs: dict[str, set] = {nd: set() for nd in nodes}
    for m in missions:
        for obj in m.objectives:
            if obj.source and obj.destination:
                s = resolved.get(obj.source)
                d = resolved.get(obj.destination)
                if s and d and s != d and s in nodes and d in nodes:
                    prereqs[d].add(s)

    nd_list = list(nodes.keys())
    n       = len(nd_list)

    def _pickup_scu(nd):
        return sum(a["scu"] for a in nodes[nd]["pickups"])

    def _deliver_scu(nd):
        return sum(a["scu"] for a in nodes[nd]["delivers"])

    best_dist  = [float("inf")]
    best_order: list[list] = [nd_list[:]]

    if n <= 10:
        # Backtracking avec élagage
        def _bt(cur, remaining, order, cur_dist, cur_scu):
            if not remaining:
                if cur_dist < best_dist[0]:
                    best_dist[0] = cur_dist
                    best_order[0] = list(order)
                return
            done = set(order)
            for i in range(len(remaining)):
                nd = remaining[i]
                if prereqs.get(nd, set()) - done:
                    continue   # prérequis non satisfaits
                # Livrer d'abord (libérer de la place), puis charger
                scu_after = cur_scu - _deliver_scu(nd) + _pickup_scu(nd)
                if scu_after > ship_scu + 0.01:
                    continue   # dépassement capacité
                d = _dist_val(dist, cur, nd)
                if cur_dist + d >= best_dist[0]:
                    continue   # élagage
                remaining.pop(i)
                order.append(nd)
                _bt(nd, remaining, order, cur_dist + d, scu_after)
                order.pop()
                remaining.insert(i, nd)

        _bt(start_node, nd_list[:], [], 0.0, 0.0)
        # Fallback si aucun ordre valide (contraintes intenables)
        if not best_order[0]:
            best_order[0] = nd_list[:]

    else:
        # Plus proche voisin avec contraintes
        order, done_set = [], set()
        cur, cur_scu = start_node, 0.0
        total_d = 0.0
        remaining = nd_list[:]
        while remaining:
            candidates = [
                nd for nd in remaining
                if not (prereqs.get(nd, set()) - done_set)
                and cur_scu - _deliver_scu(nd) + _pickup_scu(nd) <= ship_scu + 0.01
            ] or remaining
            nxt = min(candidates, key=lambda nd: _dist_val(dist, cur, nd))
            total_d += _dist_val(dist, cur, nxt)
            cur_scu  = cur_scu - _deliver_scu(nxt) + _pickup_scu(nxt)
            order.append(nxt)
            done_set.add(nxt)
            remaining.remove(nxt)
            cur = nxt
        best_order[0] = order
        best_dist[0]  = total_d

    return best_order[0], best_dist[0], nodes


def _route_detail(
    ordered_nodes: list[str],
    nodes:         dict,
    missions:      list,
    dist:          dict,
    start_node:    str | None,
    ship_scu:      float = 0,
) -> list[dict]:
    """
    Construit le détail étape par étape de la route (pour affichage et overlay).

    Chaque entrée :
      node, raw, transit_gm, delivers (list), pickups (list),
      cargo_after (SCU cumulé après arrêt), loading_order (ordre de chargement LIFO).
    """
    # Pour l'ordre de chargement LIFO, on a besoin de savoir à quelle étape
    # chaque cargaison sera livrée.
    deliver_step: dict[tuple, int] = {}   # (mi, commodity) → index d'étape
    for step_idx, nd in enumerate(ordered_nodes):
        for a in nodes[nd]["delivers"]:
            key = (a["mi"], a["commodity"])
            deliver_step.setdefault(key, step_idx)

    result = []
    cur_node = start_node
    running_scu = 0.0

    for step_idx, nd in enumerate(ordered_nodes):
        nd_data    = nodes[nd]
        transit_gm = dist.get((cur_node, nd)) if cur_node else None

        # Livraisons d'abord (libérer soute)
        delivers = [
            {
                "mission_name": missions[a["mi"]].name if a["mi"] < len(missions) else "?",
                "commodity":    a["commodity"],
                "scu":          a["scu"],
            }
            for a in nd_data["delivers"]
        ]
        running_scu -= sum(a["scu"] for a in nd_data["delivers"])

        # Chargements ensuite
        pickups = [
            {
                "mission_name": missions[a["mi"]].name if a["mi"] < len(missions) else "?",
                "commodity":    a["commodity"],
                "scu":          a["scu"],
            }
            for a in nd_data["pickups"]
        ]
        running_scu += sum(a["scu"] for a in nd_data["pickups"])

        # Ordre de chargement LIFO : ce qui est livré en DERNIER s'charge en PREMIER
        loading_order = sorted(
            nd_data["pickups"],
            key=lambda a: deliver_step.get((a["mi"], a["commodity"]), 999),
            reverse=True,
        ) if nd_data["pickups"] else []

        result.append({
            "node":          nd,
            "raw":           nd_data["raw"],
            "transit_gm":    transit_gm,
            "delivers":      delivers,
            "pickups":       pickups,
            "cargo_after":   max(0.0, running_scu),
            "ship_scu":      ship_scu,
            "loading_order": [
                {
                    "commodity": a["commodity"],
                    "scu":       a["scu"],
                    "mission":   missions[a["mi"]].name if a["mi"] < len(missions) else "?",
                }
                for a in loading_order
            ],
        })
        cur_node = nd

    return result


def _active_ship(player):
    """Retourne le vaisseau actif du joueur (active_ship en priorité)."""
    if not player or not player.ships:
        return None
    if player.active_ship:
        for s in player.ships:
            if s.name.lower() == player.active_ship.lower():
                return s
    return None


def _run_analysis(voyage: Voyage, ctx) -> None:
    mm = ctx.mission_manager
    missions = [m for m in (mm.get(str(mid)) for mid in voyage.mission_ids) if m]
    if not missions:
        print_warn("Aucune mission à analyser")
        return

    section(f"Analyse — {voyage.name}")

    total_scu = sum(m.total_scu for m in missions)
    total_rew = sum(m.reward_uec for m in missions)
    rew_str = f"{total_rew:,}".replace(",", " ")

    # ── Vaisseau actif ────────────────────────────────────────────────────────
    player = ctx.player
    ship_scu = 0
    current_ship = _active_ship(player)
    if current_ship:
        ship_scu = current_ship.scu or 0
        if ship_scu < total_scu:
            print_warn(
                f"Vaisseau actif [{C.UEX}]{current_ship.name}[/{C.UEX}] "
                f"({ship_scu} SCU) insuffisant — {total_scu:.0f} SCU requis"
            )
        else:
            console.print(
                f"  [bold]Vaisseau :[/bold] [{C.UEX}]{current_ship.name}[/{C.UEX}]"
                f"  [{C.DIM}]{ship_scu} SCU — {total_scu:.0f} utilisés[/{C.DIM}]"
            )
    elif player and player.ships:
        suitable = [s for s in player.ships if (s.scu or 0) >= total_scu]
        if suitable:
            best_ship = min(suitable, key=lambda s: s.scu or 0)
            ship_scu = best_ship.scu or 0
            console.print(
                f"  [{C.DIM}]Aucun vaisseau actif — suggestion : "
                f"[/{C.DIM}][{C.UEX}]{best_ship.name}[/{C.UEX}]"
                f"  [{C.DIM}]({ship_scu} SCU)[/{C.DIM}]"
            )
        else:
            biggest = max(player.ships, key=lambda s: s.scu or 0)
            ship_scu = biggest.scu or 0
            print_warn(f"Aucun vaisseau assez grand ({total_scu:.0f} SCU requis)")
    else:
        print_warn("Aucun vaisseau configuré — /player ship <nom> <scu>")

    # ── Résolution des lieux + calcul des distances ───────────────────────────
    graph = ctx.cache.transport_graph
    if not graph:
        print_warn("Graphe de transport indisponible")
        return

    console.print(f"\n  [{C.DIM}]Résolution des lieux et calcul des distances…[/{C.DIM}]")

    start_raw = voyage.departure or (player.location if player else None) or ""
    raw_locs: list[str] = []
    if start_raw:
        raw_locs.append(start_raw)
    for m in missions:
        for loc in m.all_sources + m.all_destinations:
            if loc and loc not in raw_locs:
                raw_locs.append(loc)

    resolved = _resolve_locs(raw_locs, graph)

    # Afficher les résolutions non trouvées
    missing = [r for r in raw_locs if not resolved.get(r)]
    if missing:
        console.print(
            f"  [{C.WARNING}]Lieux non résolus dans le graphe : "
            f"{', '.join(missing)}[/{C.WARNING}]"
        )

    # Matrice de distances sur les nœuds résolus (dédupliqués)
    node_list = list(dict.fromkeys(v for v in resolved.values() if v))
    dist = _build_dist_matrix(graph, node_list)

    start_node = resolved.get(start_raw) if start_raw else None
    if not start_node and missions[0].all_sources:
        start_node = resolved.get(missions[0].all_sources[0])

    # ── TSP ───────────────────────────────────────────────────────────────────
    if len(missions) <= 8:
        order, tour_dist = _tsp_brute_force(start_node, missions, resolved, dist)
        algo = "exhaustif"
    else:
        order, tour_dist = _tsp_nearest_neighbor(start_node, missions, resolved, dist)

    # --boucle : ajouter le retour au départ
    if voyage.loop and start_node and order:
        last_m = missions[order[-1]]
        last_raw = (last_m.all_destinations[0] if last_m.all_destinations
                    else last_m.all_sources[0] if last_m.all_sources else None)
        last_node = resolved.get(last_raw) if last_raw else None
        return_d = dist.get((last_node, start_node))
        if return_d is not None:
            tour_dist += return_d
        algo = "heuristique"

    console.print(
        f"\n  [bold]Route optimisée[/bold] [{C.DIM}]({algo})[/{C.DIM}] ·"
        f" distance totale : [bold]{_fmt_dist(tour_dist)}[/bold]\n"
    )

    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("Étape", style=C.DIM, width=5, justify="right")
    tbl.add_column("Mission", style=C.LABEL, max_width=22)
    tbl.add_column("Départ", style=C.UEX, max_width=16)
    tbl.add_column("→", style=C.DIM, width=1)
    tbl.add_column("Arrivée", style=C.UEX, max_width=16)
    tbl.add_column("Trajet", justify="right", width=8)
    tbl.add_column("Leg", justify="right", width=8)
    tbl.add_column("SCU", justify="right", width=4)
    tbl.add_column("Récompense", justify="right", width=12)

    cur_node = start_node
    cumul = 0.0
    for step, i in enumerate(order, 1):
        m = missions[i]
        src_raw = m.all_sources[0] if m.all_sources else None
        dst_raw = m.all_destinations[0] if m.all_destinations else None
        src_node = resolved.get(src_raw) if src_raw else None
        dst_node = resolved.get(dst_raw) if dst_raw else None
        travel = dist.get((cur_node, src_node)) if cur_node and src_node else None
        leg    = dist.get((src_node, dst_node)) if src_node and dst_node else None
        cumul += (travel or 0.0) + (leg or 0.0)
        scu_s = f"{m.total_scu:.0f}□" if m.total_scu else "—"
        rew_s = f"{m.reward_uec:,}".replace(",", " ")
        tbl.add_row(
            str(step),
            m.name,
            src_raw or "—",
            "→",
            dst_raw or "—",
            _fmt_dist(travel),
            _fmt_dist(leg),
            scu_s,
            rew_s + " aUEC",
        )
        cur_node = dst_node or src_node

    console.print(tbl)
    console.print(
        f"\n  [{C.DIM}]{len(missions)} mission(s) · "
        f"[bold]{total_scu:.0f}[/bold] SCU · "
        f"[bold]{rew_str}[/bold] aUEC · "
        f"distance cumulée [bold]{_fmt_dist(cumul)}[/bold][/{C.DIM}]"
    )

    # ── Suggestions de rentabilité ────────────────────────────────────────────
    spare_scu = ship_scu - total_scu
    if spare_scu >= 1:
        _suggest_cargo(missions, order, spare_scu, resolved, dist, ctx)


def _suggest_cargo(missions: list, order: list[int], spare_scu: float,
                   resolved: dict, dist: dict, ctx) -> None:
    """Propose des cargaisons rentables pour remplir le SCU disponible."""
    try:
        from uexinfo.api.uex_client import UEXClient
        client = UEXClient(ctx.cfg.get("api_key", ""))
    except Exception:
        return

    console.print(f"\n  [bold]Cargo supplémentaire disponible :[/bold] [{C.DIM}]{spare_scu:.0f} SCU libres[/{C.DIM}]")

    # Collecter les legs du voyage optimisé (départ_leg, arrivée_leg)
    legs: list[tuple[str, str]] = []
    for i in order:
        m = missions[i]
        src = m.all_sources[0] if m.all_sources else None
        dst = m.all_destinations[0] if m.all_destinations else None
        if src and dst:
            legs.append((src, dst))

    if not legs:
        return

    # Pour chaque leg, chercher les meilleures routes commerciales
    suggestions: list[tuple[float, str, str, str, float, float]] = []
    # (profit_par_scu, commodity, from, to, buy_price, sell_price)

    cache = ctx.cache
    if not cache:
        return

    for from_loc, to_loc in legs[:3]:  # limiter aux 3 premiers legs
        from_terminals = _loc_terminals(from_loc, cache)
        to_terminals   = _loc_terminals(to_loc,   cache)
        if not from_terminals or not to_terminals:
            continue
        for ft in from_terminals[:2]:
            for tt in to_terminals[:2]:
                try:
                    prices = client.get_prices(terminal_name=ft.name)
                    buys = {p.commodity_name: p for p in prices if p.operation == "buy"}
                except Exception:
                    continue
                try:
                    prices2 = client.get_prices(terminal_name=tt.name)
                    sells = {p.commodity_name: p for p in prices2 if p.operation == "sell"}
                except Exception:
                    continue
                for name, bp in buys.items():
                    if name not in sells:
                        continue
                    sp = sells[name]
                    if not bp.price or not sp.price:
                        continue
                    profit = sp.price - bp.price
                    if profit > 0:
                        suggestions.append((profit, name, ft.name, tt.name, bp.price, sp.price))

    if not suggestions:
        console.print(f"  [{C.DIM}]Aucune opportunité commerciale détectée sur ces legs.[/{C.DIM}]")
        return

    suggestions.sort(reverse=True)
    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("Commodité", style=C.LABEL, max_width=18)
    tbl.add_column("De", style=C.DIM, max_width=16)
    tbl.add_column("→", style=C.DIM, width=1)
    tbl.add_column("Vers", style=C.DIM, max_width=16)
    tbl.add_column("Profit/SCU", justify="right", width=10)
    tbl.add_column("Profit total", justify="right", width=12)

    seen: set[str] = set()
    shown = 0
    for profit, name, frm, to, buy, sell in suggestions:
        key = f"{name}|{frm}|{to}"
        if key in seen:
            continue
        seen.add(key)
        total_p = profit * spare_scu
        tp_str = f"{total_p:,.0f}".replace(",", " ") + " aUEC"
        pp_str = f"{profit:,.0f}".replace(",", " ") + " aUEC"
        tbl.add_row(name, frm, "→", to, pp_str, f"[bold {C.PROFIT}]{tp_str}[/bold {C.PROFIT}]")
        shown += 1
        if shown >= 5:
            break

    if shown:
        console.print(tbl)


def _loc_terminals(loc_name: str, cache) -> list:
    """Retourne les terminaux proches d'un lieu (par nom)."""
    name_l = loc_name.lower()
    return [
        t for t in (cache.terminals or [])
        if (t.name or "").lower() == name_l
        or name_l in (t.name or "").lower()
    ][:3]


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
        ("on [n|nom]",      "Active un voyage existant ou en crée un nouveau"),
        ("off",             "Désactive le voyage courant (conservé)"),
        ("new [nom]",       "Crée un voyage vide + l'active"),
        ("calc court",      "Voyage calculé : distance totale minimale"),
        ("calc benefice",   "Voyage calculé : bénéfice maximal (aUEC)"),
        ("calc roi",        "Voyage calculé : meilleur retour/investissement"),
        ("  --boucle",      "  Option : inclure le retour au point de départ"),
        ("  --todest <l>",  "  Option : terminer à ce lieu"),
        ("  --to <l>",      "  Option : passer par ce lieu (missions prioritaires)"),
        ("  --exclude <l>", "  Option : exclure les missions touchant ce lieu"),
        ("  --station",     "  Option : stations spatiales uniquement"),
        ("<nom|n>",         "Active le voyage (ou /voyage <nom> list pour afficher)"),
        ("name <nom>",      "Renomme le voyage actif"),
        ("list [--trajets]","Missions du voyage actif, ou tous les voyages"),
        ("add [m1 m2...]",  "Ajoute des missions (catalogue) au voyage actif"),
        ("remove <m>",      "Retire une mission du voyage"),
        ("clear",           "Vide les missions du voyage actif (conserve le voyage)"),
        ("delete [n…|--all]","Supprime un ou plusieurs voyages (sélecteur si sans args)"),
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
