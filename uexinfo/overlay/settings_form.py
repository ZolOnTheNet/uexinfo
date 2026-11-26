"""Réglages en formulaire (⚙ de la barre d'état, `/config edit`) : onglets, champs, valeurs permises.

Chaque champ lit une clé de config.toml et s'enregistre par une commande qui existe déjà
(`cmd`, où `{v}` est la valeur choisie) : formulaire et saisie passent par le même
dispatch, avec les mêmes contrôles. Un champ à mots-clés est une liste déroulante, chaque
mot-clé suivi de son explication.

Seuls les réglages que le code lit sont là (vérifié le 2026-10-30). Jamais lus, donc
absents : trade.min_profit_per_scu, trade.min_margin_percent, trade.max_distance,
trade.illegal_commodities, sctrade.ttl, dev.*, voyage.calc.favoris (voir docs/ai/NOTES.md).
`tests/test_settings_form.py` passe chaque commande et vérifie la valeur enregistrée.
"""
from __future__ import annotations

from uexinfo.config.settings import DEFAULT


def _field(kind: str, key: str, label: str, cmd: str, help: str = "", **extra) -> dict:
    """Champ lié à la clé pointée `key` de la config ; `cmd` l'enregistre."""
    return {"kind": kind, "key": key, "label": label, "cmd": cmd,
            **({"help": help} if help else {}), **extra}


def _choice(key: str, label: str, cmd: str, choices: list[tuple[str, str]], help: str = "") -> dict:
    """Liste déroulante : un mot-clé permis par ligne, avec son explication."""
    return _field("choice", key, label, cmd, help, choices=[{"v": v, "t": t} for v, t in choices])


def _flags(key: str, label: str, cmd: str, choices: list[tuple[str, str]], help: str = "") -> dict:
    """Plusieurs mots-clés à cocher, enregistrés séparés par des espaces."""
    return _field("flags", key, label, cmd, help, choices=[{"v": v, "t": t} for v, t in choices])


def _number(key: str, label: str, cmd: str, lo: float, hi: float, step: float = 1,
            unit: str = "", help: str = "") -> dict:
    """Nombre borné."""
    return _field("number", key, label, cmd, help, min=lo, max=hi, step=step, unit=unit)


def _text(key: str, label: str, cmd: str, help: str = "", placeholder: str = "") -> dict:
    """Texte libre (chemin, version, raccourci)."""
    return _field("text", key, label, cmd, help, placeholder=placeholder)


def _words(key: str, label: str, cmd: str, help: str = "") -> dict:
    """Liste de mots séparés par des espaces (« _ » remplace l'espace dans un nom)."""
    return _field("words", key, label, cmd, help)


def _section(label: str) -> dict:
    """Titre d'un groupe de champs."""
    return {"kind": "section", "label": label}


def _on_off(on: str, off: str) -> list[tuple[str, str]]:
    return [("on", on), ("off", off)]


TABS: list[dict] = [
    # La flotte : liste dessinée par settings.js (clic : fiche du vaisseau, double-clic : actif)
    {"id": "ships", "label": "Vaisseaux", "icon": "✈", "fields": []},

    {"id": "overlay", "label": "Overlay", "icon": "▣", "fields": [
        _choice("overlay.mode", "Mode d'affichage", "/config mode {v}", [
            ("console", "ligne de commande seule"),
            ("mixte", "colonne de boutons à droite, et la ligne de commande"),
            ("souris", "boutons seuls, sans ligne de commande")],
            "Aussi : le bouton à gauche de ⚙."),
        _choice("overlay.close", "Bouton ✕", "/config close {v}", [
            ("normal", "✕ ferme l'overlay"),
            ("dblclick", "✕ masque l'overlay, double-clic sur ✕ le ferme")],
            "Pris en compte au prochain lancement."),
        _choice("overlay.clock", "Horloge de fond", "/config clock {v}",
                _on_off("horloge en fond de fenêtre", "pas d'horloge")),
        _number("overlay.opacity", "Opacité", "/config opacity {v}", 0.10, 0.99, 0.05, "",
                "0,10 presque transparent, 0,99 opaque. Aussi : − et + dans la barre d'état."),
        _text("overlay.hotkey", "Raccourci global", "/config hotkey {v}",
              "Affiche ou masque l'overlay. Touches liées par + : alt, ctrl, shift, puis une "
              "touche (a-z, f1-f12, esc, space…). Pris en compte au prochain lancement.",
              "alt+shift+u"),
        _number("overlay.cmdhistory", "Commandes réaffichées", "/config cmdhistory {v}", 1, 50, 1, "",
                "Dernières commandes, avec leur résultat, réaffichées au démarrage."),
    ]},

    {"id": "trade", "label": "Commerce", "icon": "$", "fields": [
        _section("Sources de prix"),
        _choice("sctrade.enabled", "sc-trade.tools", "/config sctrade {v}",
                _on_off("prix de la communauté (en orange) avec ceux de UEX",
                        "UEX et tes scans seulement")),
        _choice("commodities.shipammun", "Munitions de vaisseau", "/config commodities.shipammun {v}",
                _on_off("affichées (Ship Ammunition, Decoy, Noise…)", "masquées des listes et tableaux"),
                "Ne servent qu'au ravitaillement des gros vaisseaux."),
        _section("Contrats (/mission offres, /mission route)"),
        _number("contracts.lot_destinations", "Meilleur lot : destinations, au plus",
                "/config contracts.lot_destinations {v}", 0, 20, 1, "lieux", "0 = sans limite."),
        _number("contracts.stop_minutes", "Temps compté par arrêt", "/config contracts.stop_minutes {v}",
                0, 30, 0.5, "min", "Atterrir, hangar, décoller : ajouté au vol et au chargement."),
        _section("Voyages (/voyage calc)"),
        _number("voyage.calc.nbsaut", "Missions par voyage, au plus", "/config voyage.calc.nbsaut {v}",
                1, 20, 1, "missions"),
        _choice("voyage.calc.prop", "Propositions", "/config voyage.calc.prop {v}", [
            ("1", "le critère demandé seul"),
            ("2", "trois propositions : distance, bénéfice, ROI")]),
        _flags("voyage.calc.options", "Options par défaut", "/config voyage.calc.options {v}", [
            ("--boucle", "revenir au point de départ"),
            ("--station", "lieux en station seulement")]),
        _number("voyage.calc.gap_max", "Trajet à vide signalé ⚠", "/config voyage.calc.gap_max {v}",
                0.5, 50, 0.5, "Gm", "Trajet sans mission entre deux étapes, au-delà duquel ⚠ s'affiche."),
        _words("voyage.calc.exclure", "Lieux exclus", "/config voyage.calc.exclure {v}",
               "Noms séparés par des espaces ; _ remplace l'espace dans un nom (Port_Tressler)."),
    ]},

    {"id": "scan", "label": "Scan", "icon": "◉", "fields": [
        _section("Relevés de prix"),
        _choice("scan.mode", "Source de /scan", "/config scan mode {v}", [
            ("ocr", "la dernière capture d'écran"),
            ("log", "le log de SC-Datarunner"),
            ("confirm", "le log d'abord, sinon la capture")]),
        _choice("scan.auto_ocr", "Captures d'écran", "/config scan auto_ocr {v}",
                _on_off("lues dès leur arrivée", "lues par /scan seulement")),
        _choice("auto.log", "Log SC-Datarunner", "/auto log {v}",
                _on_off("surveillé en continu", "lu par /scan log seulement")),
        _choice("auto.log_accept", "Valeurs du log", "/auto log.accept {v}",
                _on_off("enregistrées dès leur lecture", "affichées sans être enregistrées")),
        _choice("auto.signal_scan", "Nouveaux scans", "/auto signal.scan {v}",
                _on_off("signalés", "traités sans être signalés")),
        _section("Position automatique"),
        _choice("scan.autopos", "Après tout scan", "/config scan.autopos {v}",
                _on_off("ta position devient le terminal scanné", "ta position ne change pas")),
        _choice("scan.log.autopos", "Scans du log", "/config scan.log.autopos {v}", [
            ("off", "ta position ne change pas"),
            ("on", "après /scan log : position au dernier terminal lu"),
            ("quick", "dès qu'un scan arrive dans le log")]),
        _section("Missions capturées"),
        _number("scan.hour", "Captures lues", "/config scan hour {v}", 1, 48, 1, "h",
                "Âge maximum des captures lues par /mission scan."),
        _number("scan.session_gap", "Nouvelle session après", "/config scan session_gap {v}",
                5, 600, 5, "min", "Écart entre deux captures qui commence une nouvelle session."),
        _section("Offres de contrats (mobiGlas)"),
        _choice("contracts.auto_capture", "Mode scan au lancement", "/config contracts.auto_capture {v}",
                _on_off("actif dès le lancement", "par le bouton Scan Mis. ou /mission offres on"),
                "Pris en compte au prochain lancement."),
        _choice("contracts.read_on_click", "Lecture au clic", "/config contracts.read_on_click {v}",
                _on_off("l'offre est lue après chaque clic", "lue par la touche seulement")),
        _text("contracts.hotkey", "Touche de lecture", "/config contracts.hotkey {v}",
              "Lit l'offre affichée tout de suite (f9, insert, alt+shift+m…). Vide : aucune. "
              "Pris en compte au prochain lancement du mode scan.", "f9"),
        _choice("contracts.beep", "Bip", "/config contracts.beep {v}",
                _on_off("bip quand l'offre est lue", "silencieux")),
        _number("contracts.keep_images", "Images gardées", "/config contracts.keep_images {v}",
                0, 500, 1, "", "Dernières images de l'écran Contrats, pour le dépannage (0 = aucune)."),
        _section("Fichiers"),
        _text("scan.sc_screenshots_dir", "Dossier des captures", "/config scan screenshots {v}",
              "Dossier ScreenShots du jeu."),
        _text("scan.sc_log_path", "Log SC-Datarunner", "/config scan logpath {v}",
              "Fichier app.log de SC-Datarunner."),
        _text("scan.tesseract_exe", "Tesseract", "/config scan tesseract {v}",
              "Vide : la copie fournie (extprg/tesseract), sinon celle du système."),
        _section("Game.log"),
        _choice("gamelog.enabled", "Suivi de Game.log", "/config gamelog.enabled {v}",
                _on_off("zone, juridiction et arrivées lues en direct", "pas de suivi")),
        _choice("gamelog.position", "À une arrivée", "/config gamelog.position {v}", [
            ("auto", "ta position suit le lieu atteint"),
            ("propose", "un bandeau propose le lieu"),
            ("off", "ta position ne change pas")]),
        _text("gamelog.install_path_live", "Dossier du jeu, LIVE", "/config gamelog.install_path_live {v}",
              "Le dossier qui contient Game.log, ex. C:\\Roberts Space Industries\\StarCitizen\\LIVE."),
        _text("gamelog.install_path_ptu", "Dossier du jeu, PTU", "/config gamelog.install_path_ptu {v}",
              "Facultatif."),
    ]},

    {"id": "display", "label": "Affichage et traitement", "short": "Affichage", "icon": "▤", "fields": [
        _section("Fiche d'un terminal (/info)"),
        _choice("display.magasins", "Magasins", "/config magasins {v}", _on_off("listés", "masqués")),
        _choice("display.restaurants", "Restaurants", "/config restaurants {v}", _on_off("listés", "masqués")),
        _choice("display.services", "Services", "/config services {v}", _on_off("listés", "masqués")),
        _choice("info.note", "Mes notes", "/config info note {v}", _on_off("affichées", "masquées")),
        _section("Version de Star Citizen"),
        _choice("version.active", "Serveurs", "/config version use {v}", [
            ("live", "LIVE, le jeu publié"),
            ("ptu", "PTU, les serveurs de test")],
            "Les scans d'une autre version ne sont pas repris."),
        _text("version.live", "Version LIVE", "/config version live {v}", placeholder="4.3"),
        _text("version.ptu", "Version PTU", "/config version ptu {v}", "Vide s'il n'y a pas de PTU."),
        _section("Journal du programme"),
        _number("log.days", "Jours gardés", "/config log.days {v}", 1, 90, 1, "jours",
                "Un fichier par jour dans <données uexinfo>/logs."),
        _section("Données UEX"),
        _number("cache.ttl_static", "Lieux, terminaux, vaisseaux", "/config cache ttl {v}",
                3600, 604800, 3600, "s",
                "Retéléchargés après ce délai (86400 s = 24 h). Les prix ont leur propre délai, de 4 à 72 h."),
    ]},
]


def fields() -> list[dict]:
    """Tous les champs, onglet après onglet (sans les titres de section)."""
    return [f for tab in TABS for f in tab["fields"] if f["kind"] != "section"]


def _get(cfg: dict, key: str):
    """Valeur de la clé pointée `key` : la config, sinon la valeur par défaut."""
    for src in (cfg, DEFAULT):
        node = src
        for part in key.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if node is not None:
            return node
    return None


def _show(value) -> str:
    """Valeur de config → texte du formulaire (booléen → on/off, liste → mots)."""
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, list):
        return " ".join(str(v).replace(" ", "_") for v in value)
    return "" if value is None else str(value)


def values(cfg: dict) -> dict[str, str]:
    """Valeur actuelle de chaque champ, telle que le formulaire l'affiche."""
    return {f["key"]: _show(_get(cfg, f["key"])) for f in fields()}


def command(field: dict, value: str) -> str:
    """Ligne de commande qui enregistre `value` dans le champ `field`.

    Texte avec espaces, ou vide : entre guillemets (le parseur les retire) ; liste de mots :
    telle quelle, un mot par argument.
    """
    value = str(value).strip()
    if field["kind"] in ("words", "flags"):
        arg = value or '""'
    else:
        arg = f'"{value}"' if (not value or " " in value) else value
    return field["cmd"].format(v=arg)


def set_line(key: str, value) -> str:
    """Commande d'un changement reçu de la page (`settings_set`) ; "" si la clé ou la
    valeur n'est pas permise (mot-clé hors liste, nombre hors bornes, guillemet)."""
    field = next((f for f in fields() if f["key"] == key), None)
    value = str(value).strip()
    if field is None or '"' in value or "\n" in value:
        return ""
    if field["kind"] == "choice" and value not in {c["v"] for c in field["choices"]}:
        return ""
    if field["kind"] == "flags" and not set(value.split()) <= {c["v"] for c in field["choices"]}:
        return ""
    if field["kind"] == "number":
        try:
            n = float(value.replace(",", "."))
        except ValueError:
            return ""
        if not field["min"] <= n <= field["max"]:
            return ""
        value = str(int(n)) if float(field["step"]).is_integer() else str(n)
    return command(field, value)


def ship_line(action: str, name: str, data: dict) -> str:
    """Commande d'une action sur la flotte reçue de la page (`settings_ship`) ; "" sinon.

    set / remove / add : nom du vaisseau ; cargo : `cargo` {taille: nombre} et `scu`.
    """
    from uexinfo.data.cargo_grids import VALID_SIZES
    name = str(name).strip()
    if not name or '"' in name:
        return ""
    if action == "add":
        return f"/ship add {name}"
    if action in ("set", "remove"):
        return f'/ship {action} "{name}"'
    if action == "cargo":
        try:
            grid = {int(k): int(n) for k, n in (data.get("cargo") or {}).items()}
            scu = int(data.get("scu") or 0)
        except (TypeError, ValueError):
            return ""
        if not set(grid) <= VALID_SIZES or min(grid.values(), default=0) < 0 or scu < 0:
            return ""
        specs = [f"{n}x{k}" for k, n in sorted(grid.items(), reverse=True) if n] or ["0x32"]
        return f'/ship cargo "{name}" {" ".join(specs)} {scu}'
    return ""


def ships(ctx) -> list[dict]:
    """La flotte du joueur pour le formulaire : nom, SCU, conteneurs, et le modèle UEX."""
    from uexinfo.names import norm
    vehicles = {}
    for v in getattr(ctx.cache, "vehicles", None) or []:
        for k in (v.name_full, v.name):
            if k:
                vehicles.setdefault(norm(k), v)
    grids = getattr(ctx, "cargo_grid_manager", None)
    out = []
    for s in ctx.player.ships:
        v = vehicles.get(norm(s.name))
        grid = grids.get_grid(s.name) if grids else None
        out.append({
            "name":   s.name,
            "scu":    s.scu or 0,
            "active": s.name == ctx.player.active_ship,
            "cargo":  {str(k): n for k, n in sorted(s.cargo_config.items(), reverse=True)},
            "model":  {
                "scu":  v.scu if v else 0,
                "pad":  v.pad_type if v else "",
                "maker": v.manufacturer if v else "",
                "grid": {str(k): n for k, n in sorted((grid or {}).items(), reverse=True)},
            } if (v or grid) else None,
        })
    return out


WIDTH_MIN, WIDTH_MAX = 420, 2000   # largeur du tiroir en px ; au minimum, les 5 onglets tiennent


def width(cfg) -> int:
    """Largeur enregistrée du tiroir des réglages, bornée."""
    try:
        w = int(_get(cfg, "overlay.settings_width"))
    except (TypeError, ValueError):
        w = DEFAULT["overlay"]["settings_width"]
    return max(WIDTH_MIN, min(WIDTH_MAX, w))


def store_width(cfg, value) -> bool:
    """Retient la largeur choisie à la souris ; False si la valeur est invalide ou inchangée."""
    try:
        w = max(WIDTH_MIN, min(WIDTH_MAX, int(float(value))))
    except (TypeError, ValueError):
        return False
    ov = cfg.setdefault("overlay", {})
    if ov.get("settings_width") == w:
        return False
    ov["settings_width"] = w
    return True


def state(ctx) -> dict:
    """Message `settings` : valeurs des champs et flotte du joueur."""
    return {"type": "settings", "values": values(ctx.cfg), "ships": ships(ctx)}


def schema(ctx) -> dict:
    """Message `settings_schema`, envoyé à la connexion : onglets, champs, tailles de
    conteneurs et noms des vaisseaux UEX (pour l'ajout)."""
    from uexinfo.data.cargo_grids import VALID_SIZES
    return {
        "type":     "settings_schema",
        "tabs":     TABS,
        "width":    width(ctx.cfg),
        "width_min": WIDTH_MIN,
        "sizes":    sorted(VALID_SIZES, reverse=True),
        "vehicles": sorted({v.name_full for v in (getattr(ctx.cache, "vehicles", None) or [])
                            if v.name_full}),
    }
