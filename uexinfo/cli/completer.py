"""Autocomplétion contextuelle via prompt_toolkit."""
from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

if TYPE_CHECKING:
    from uexinfo.cli.main import AppContext

# Sous-commandes statiques connues
_EXPLORE_ROOTS = ["ship", "commodity"]  # + system names (dynamic)

_SUBS: dict[str, list[str]] = {
    "help":                 [],
    "ship":                 ["list", "add", "remove", "set", "cargo"],
    "config":               ["ship", "trade", "cache", "scan", "player"],
    "config ship":          ["list", "add", "remove", "set", "cargo"],
    "config trade":         ["profit", "margin", "illegal"],
    "config cache":         ["ttl", "clear"],
    "config scan":          ["mode", "tesseract", "logpath", "screenshots"],
    "config scan mode":     ["ocr", "log", "confirm"],
    "go":                   ["from", "to", "clear"],
    "lieu":                 ["from", "to", "clear"],
    "player":               ["info", "ship", "dest"],
    "player ship":          ["add", "set", "scu", "remove"],
    "scan":                 ["ecran", "screen", "screenshot", "log", "status", "history"],
    "select":               ["system", "planet", "station", "terminal", "city", "outpost",
                             "add", "remove", "clear"],
    "select add":           ["system", "planet", "station", "terminal", "city", "outpost"],
    "select remove":        ["system", "planet", "station", "terminal", "city", "outpost"],
    "trade":                ["buy", "sell", "best", "compare"],
    "trade best":           ["--profit", "--roi", "--margin", "--scu"],
    "route":                ["from", "to", "--commodity", "--min-profit", "--scu"],
    "plan":                 ["new", "add", "remove", "optimize", "clear", "show"],
    "info":                 ["terminal", "commodity", "ship"],
    "info ship":            [],  # completions dynamiques (noms de vaisseaux)
    "explore":              [],  # completions are fully dynamic
    "refresh":              ["all", "static", "prices", "sctrade", "status"],
    "exit":                 [],
    "quit":                 [],
    "bye":                  [],
}

_ALL_COMMANDS = sorted({k.split()[0] for k in _SUBS})

# Commandes qui complètent avec des noms de commodités
_COMMODITY_CMDS = {"trade", "info"}
# Commandes qui complètent avec des noms de terminaux
_TERMINAL_CMDS = {"go", "lieu", "route", "info"}


class UEXCompleter(Completer):
    def __init__(self, ctx: "AppContext | None" = None):
        self.ctx = ctx

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor

        # Détecter si le dernier token commence par @
        words_raw = text.split()
        last_word = words_raw[-1] if words_raw else ""
        if last_word.startswith("@"):
            yield from self._complete_location(last_word)
            return

        text = text.lstrip()

        if not text.startswith("/"):
            # Saisie libre → complétion /info (terminaux + commodités)
            if self.ctx and len(text) >= 1:
                yield from self._complete_info_query(text)
            return

        after = text[1:]
        words = after.split()
        ends_space = text.endswith(" ")

        # ── Complétion du nom de commande ────────────────────────────────
        if not words or (len(words) == 1 and not ends_space):
            prefix = words[0].lower() if words else ""
            for cmd in _ALL_COMMANDS:
                if cmd.startswith(prefix):
                    yield Completion(cmd, start_position=-len(prefix))
            return

        cmd = words[0].lower()

        # ── Complétion des sous-commandes ────────────────────────────────
        if ends_space:
            typed_args = words[1:]
            current = ""
        else:
            typed_args = words[1:-1]
            current = words[-1] if len(words) > 1 else ""

        # Construire la clé de contexte
        context_key = cmd
        if typed_args:
            context_key = f"{cmd} {typed_args[0].lower()}"

        candidates = _SUBS.get(context_key, [])
        if not candidates and not typed_args:
            candidates = _SUBS.get(cmd, [])

        cur_lower = current.lower()
        for c in candidates:
            if c.startswith(cur_lower):
                yield Completion(c, start_position=-len(current))

        # ── Complétion dynamique : commodités ────────────────────────────
        if self.ctx and cmd in _COMMODITY_CMDS and (ends_space or len(words) >= 2):
            for c in self.ctx.cache.commodities:
                name = c.name
                if name.lower().startswith(cur_lower):
                    yield Completion(
                        name,
                        start_position=-len(current),
                        display=f"{name}  ({c.code})",
                        display_meta=c.kind,
                    )

        # ── Complétion dynamique : terminaux ─────────────────────────────
        if self.ctx and cmd in _TERMINAL_CMDS and (ends_space or len(words) >= 2) and cur_lower:
            if self.ctx.location_index:
                for entry in self.ctx.location_index.search(current, limit=12, types={"terminal"}):
                    slug = entry.name.replace(" ", "_")
                    yield Completion(
                        slug,
                        start_position=-len(current),
                        display=entry.name,
                        display_meta=entry.full_path,
                    )
            else:
                for t in self.ctx.cache.terminals:
                    name = t.name
                    if name.lower().startswith(cur_lower):
                        yield Completion(
                            name,
                            start_position=-len(current),
                            display=name,
                            display_meta=t.location,
                        )

        # ── Complétion dynamique : vaisseaux (ship / config ship / player ship) ────
        is_ship_cmd = (
            cmd == "ship" or
            (cmd == "config" and typed_args and typed_args[0] == "ship") or
            (cmd == "player" and typed_args and typed_args[0] == "ship")
        )
        if self.ctx and is_ship_cmd:
            # Pour /ship <action>, l'action est typed_args[0]
            # Pour /config ship <action> et /player ship <action>, c'est typed_args[1]
            if cmd == "ship":
                action = typed_args[0].lower() if typed_args else ""
            else:
                action = typed_args[1].lower() if len(typed_args) > 1 else ""
            if action in ("add", ""):
                cur_norm = cur_lower.replace("_", " ")
                # Priorité 1 : préfixe du nom complet
                seen_v: set[str] = set()
                for v in (self.ctx.cache.vehicles or []):
                    if v.name_full.lower().startswith(cur_norm):
                        slug = v.name_full.replace(" ", "_")
                        seen_v.add(v.name_full)
                        yield Completion(
                            slug, start_position=-len(current),
                            display=v.name_full, display_meta=v.manufacturer,
                        )
                # Priorité 2 : n'importe quel mot du nom commence par la query
                if cur_norm and len(cur_norm) >= 2:
                    for v in (self.ctx.cache.vehicles or []):
                        if v.name_full in seen_v:
                            continue
                        if any(w.startswith(cur_norm) for w in v.name_full.lower().split()):
                            slug = v.name_full.replace(" ", "_")
                            seen_v.add(v.name_full)
                            yield Completion(
                                slug, start_position=-len(current),
                                display=v.name_full, display_meta=v.manufacturer,
                            )
            elif action in ("remove", "cargo", "set"):
                # Seulement les vaisseaux déjà configurés
                for ship in (self.ctx.player.ships if hasattr(self.ctx, 'player') else []):
                    if ship.name.lower().startswith(cur_lower):
                        slug = ship.name.replace(" ", "_")
                        scu_info = f"{ship.scu} SCU" if ship.scu else "? SCU"
                        yield Completion(
                            slug,
                            start_position=-len(current),
                            display=ship.name,
                            display_meta=scu_info,
                        )

        # ── Complétion dynamique : /info ship <nom> ou /info <nom_vaisseau> ─
        if self.ctx and cmd == "info" and (
            (typed_args and typed_args[0].lower() == "ship") or
            (not typed_args and (ends_space or len(words) >= 2))
        ):
            cur_norm = cur_lower.replace("_", " ")
            seen_vs: set[str] = set()
            for v in (self.ctx.cache.vehicles or []):
                if v.name_full.lower().startswith(cur_norm):
                    slug = v.name_full.replace(" ", "_")
                    seen_vs.add(v.name_full)
                    yield Completion(slug, start_position=-len(current),
                                     display=v.name_full, display_meta=v.manufacturer)
            if cur_norm and len(cur_norm) >= 2:
                for v in (self.ctx.cache.vehicles or []):
                    if v.name_full in seen_vs:
                        continue
                    if any(w.startswith(cur_norm) for w in v.name_full.lower().split()):
                        slug = v.name_full.replace(" ", "_")
                        seen_vs.add(v.name_full)
                        yield Completion(slug, start_position=-len(current),
                                         display=v.name_full, display_meta=v.manufacturer)

        # ── Complétion dynamique : /explore ──────────────────────────────
        if self.ctx and cmd == "explore":
            yield from self._complete_explore(current, ends_space, typed_args)

    def _complete_explore(self, current: str, ends_space: bool, typed_args: list[str]):
        """Complétion pour /explore — navigation par point."""
        if not self.ctx:
            return

        # Le premier (et unique) arg de /explore est un chemin point.
        # Si ends_space et pas d'arg : compléter le premier niveau
        # Si un arg est en cours de frappe : compléter la dernière partie après le dernier "."
        raw_path = typed_args[0] if typed_args else current
        if ends_space:
            # L'utilisateur a tapé un espace après /explore → premier niveau
            raw_path = ""

        parts = raw_path.split(".")
        prefix_parts = parts[:-1]   # parties déjà confirmées
        last = parts[-1].lower()    # portion à compléter
        prefix_str = ".".join(prefix_parts)

        def _mk(name: str, meta: str = "") -> Completion:
            full = f"{prefix_str}.{name}" if prefix_str else name
            return Completion(
                full,
                start_position=-len(raw_path),
                display=full,
                display_meta=meta,
            )

        depth = len(prefix_parts)

        if depth == 0:
            # Premier niveau : systèmes + "ship" + "commodity"
            roots = (
                [s.name.lower() for s in self.ctx.cache.star_systems]
                + ["ship", "commodity"]
            )
            for r in sorted(set(roots)):
                if r.startswith(last):
                    yield _mk(r)
            return

        root = prefix_parts[0].lower()

        if root == "ship" and depth == 1:
            # Niveau 1 : slugs de fabricants (1er mot, sans espace)
            slug_to_mfr: dict[str, str] = {}
            for v in (self.ctx.cache.vehicles or []):
                mfr = v.manufacturer or "Autre"
                slug = mfr.lower().split()[0]
                slug_to_mfr.setdefault(slug, mfr)

            for slug, mfr_full in sorted(slug_to_mfr.items()):
                if slug.startswith(last):
                    count = sum(1 for vv in self.ctx.cache.vehicles
                                if (vv.manufacturer or "Autre") == mfr_full)
                    yield _mk(slug, f"{mfr_full} · {count}")

            # Aussi : mots de noms de vaisseaux (≥2 chars typed)
            if last and len(last) >= 2:
                seen_words: set[str] = set()
                for v in (self.ctx.cache.vehicles or []):
                    for word in v.name_full.lower().split():
                        if word.startswith(last) and word not in slug_to_mfr and word not in seen_words:
                            seen_words.add(word)
                            yield _mk(word, v.name_full)
            return

        if root == "ship" and depth == 2:
            # Niveau 2 : ship.crusader.<Tab> → noms (premiers mots) des vaisseaux du fabricant
            mfr_slug = prefix_parts[1].lower()
            vehicles = self.ctx.cache.vehicles or []
            # Filtrer par fabricant (slug match)
            mfr_ships = [v for v in vehicles
                         if (v.manufacturer or "").lower().split()[0].startswith(mfr_slug)
                         or (v.manufacturer or "").lower().startswith(mfr_slug)]
            # Proposer le premier mot significatif du nom court (sans le nom du fabricant)
            seen_words2: set[str] = set()
            for v in sorted(mfr_ships, key=lambda v: v.name_full):
                # Retirer le nom du fabricant du début de name_full pour avoir le nom court
                fname = v.name_full
                for mfr_word in (v.manufacturer or "").split():
                    if fname.lower().startswith(mfr_word.lower()):
                        fname = fname[len(mfr_word):].strip()
                key_word = fname.split()[0].lower() if fname.split() else v.name.lower()
                if key_word.startswith(last) and key_word not in seen_words2:
                    seen_words2.add(key_word)
                    yield _mk(key_word, v.name_full)
            return

        if root == "commodity":
            seen_kinds: set[str] = set()
            for c in self.ctx.cache.commodities:
                k = (c.kind or "autre").lower()
                if k not in seen_kinds and k.startswith(last):
                    seen_kinds.add(k)
                    yield _mk(k)
            return

        # Géo
        sys_name = next(
            (s.name for s in self.ctx.cache.star_systems if s.name.lower() == root),
            None,
        )
        if not sys_name:
            return

        sys_terminals = [t for t in self.ctx.cache.terminals if t.star_system_name == sys_name]

        if depth == 1:
            bodies = {(t.planet_name or t.orbit_name or "?").lower() for t in sys_terminals}
            for b in sorted(bodies):
                if b.startswith(last):
                    yield _mk(b)
        elif depth == 2:
            body_q = prefix_parts[1].lower()
            body_terms = [
                t for t in sys_terminals
                if (t.planet_name or t.orbit_name or "?").lower().startswith(body_q)
            ]
            locs = {t.name.rsplit(" - ", 1)[-1].strip().lower() for t in body_terms}
            for loc in sorted(locs):
                if loc.startswith(last):
                    yield _mk(loc)

    def _complete_info_query(self, text: str):
        """Complétion pour la saisie libre — terminaux, commodités, vaisseaux."""
        text_norm = text.replace("_", " ")
        q         = text_norm.lower()
        start     = -len(text)

        # ── Terminaux ─────────────────────────────────────────────────────
        seen_t: set[str] = set()
        if self.ctx.location_index:
            for entry in self.ctx.location_index.search(text_norm, limit=8, types={"terminal"}):
                slug = entry.name.replace(" ", "_")
                if slug in seen_t:
                    continue
                seen_t.add(slug)
                yield Completion(
                    slug,
                    start_position=start,
                    display=entry.name,
                    display_meta=f"terminal · {entry.full_path}",
                )

        # ── Commodités (préfixe d'abord, puis sous-chaîne) ────────────────
        seen_c: set[str] = set()
        for c in (self.ctx.cache.commodities or []):
            if c.name.lower().startswith(q):
                slug = c.name.replace(" ", "_")
                if slug not in seen_c:
                    seen_c.add(slug)
                    yield Completion(
                        slug,
                        start_position=start,
                        display=f"{c.name}  ({c.code})",
                        display_meta=c.kind or "commodité",
                    )
        for c in (self.ctx.cache.commodities or []):
            slug = c.name.replace(" ", "_")
            if q in c.name.lower() and slug not in seen_c:
                seen_c.add(slug)
                yield Completion(
                    slug,
                    start_position=start,
                    display=f"{c.name}  ({c.code})",
                    display_meta=c.kind or "commodité",
                )

        # ── Vaisseaux (préfixe d'abord, puis mot interne) ─────────────────
        seen_v: set[str] = set()
        for v in (self.ctx.cache.vehicles or []):
            if v.name_full.lower().startswith(q):
                slug = v.name_full.replace(" ", "_")
                if slug not in seen_v:
                    seen_v.add(slug)
                    yield Completion(
                        slug,
                        start_position=start,
                        display=v.name_full,
                        display_meta=f"vaisseau · {v.manufacturer}",
                    )
        if q and len(q) >= 2:
            for v in (self.ctx.cache.vehicles or []):
                slug = v.name_full.replace(" ", "_")
                if slug in seen_v:
                    continue
                if any(w.startswith(q) for w in v.name_full.lower().split()):
                    seen_v.add(slug)
                    yield Completion(
                        slug,
                        start_position=start,
                        display=v.name_full,
                        display_meta=f"vaisseau · {v.manufacturer}",
                    )

    def _complete_location(self, token: str):
        """Complète un token @xxx avec le LocationIndex."""
        if self.ctx is None or self.ctx.location_index is None:
            return

        query = token[1:]  # retirer le @
        entries = self.ctx.location_index.search(query, limit=15)

        if not entries:
            # Retour visuel quand aucun lieu ne correspond
            yield Completion(
                token,
                start_position=-len(token),
                display=f"@… aucun lieu trouvé pour « {query} »",
                display_meta="",
            )
            return

        for entry in entries:
            # Si query contient un "." on propose le full_path, sinon juste le nom
            if "." in query:
                completion_text = f"@{entry.full_path}"
            else:
                completion_text = f"@{entry.name}"

            yield Completion(
                completion_text,
                start_position=-len(token),
                display=completion_text,
                display_meta=f"{entry.type} · {entry.full_path}",
            )
