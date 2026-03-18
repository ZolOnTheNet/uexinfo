"""Serveur WebSocket overlay — reçoit les commandes du frontend HTML et retourne
la sortie Rich (ANSI) + les mises à jour de statut.

IMPORTANT : ce module doit être importé AVANT tout autre module uexinfo qui
utilise `uexinfo.display.formatter.console`, car il redirige ce console vers
un StringIO interne.
"""
from __future__ import annotations

# ── 1. Redirect console AVANT l'import des commandes ─────────────────────────
import io as _io
import uexinfo.display.formatter as _fmt_mod
from rich.console import Console as _RichConsole

_buf = _io.StringIO()
_fmt_mod.console = _RichConsole(
    file=_buf,
    force_terminal=True,
    markup=True,
    highlight=True,
    width=100,
)

# ── 2. Imports normaux ────────────────────────────────────────────────────────
import asyncio
import json
import os
import re
import threading
from pathlib import Path

import websockets
import websockets.exceptions

# Enregistrer toutes les commandes CLI
import uexinfo.cli.commands.help         # noqa: F401
import uexinfo.cli.commands.config       # noqa: F401
import uexinfo.cli.commands.refresh      # noqa: F401
import uexinfo.cli.commands.go           # noqa: F401
import uexinfo.cli.commands.select       # noqa: F401
import uexinfo.cli.commands.player       # noqa: F401
import uexinfo.cli.commands.scan         # noqa: F401
import uexinfo.cli.commands.info         # noqa: F401
import uexinfo.cli.commands.explore      # noqa: F401
import uexinfo.cli.commands.trade        # noqa: F401
import uexinfo.cli.commands.nav          # noqa: F401
import uexinfo.cli.commands.history_cmd  # noqa: F401
import uexinfo.cli.commands.debug        # noqa: F401
import uexinfo.cli.commands.auto         # noqa: F401
import uexinfo.cli.commands.undo         # noqa: F401

from uexinfo.cli.runner import run_command
from uexinfo.cli.main import AppContext
from uexinfo.cache.manager import CacheManager
from uexinfo.location.index import LocationIndex
from uexinfo.models.player import Player
import uexinfo.config.settings as _settings
import uexinfo.cli.history as _history_mod

_RE_ANSI = re.compile(r"\x1b\[[0-9;]*[mK]")

# Commandes qui nécessitent une mise à jour de la barre de statut
_STATUS_CMDS = frozenset({"player", "p", "go", "lieu", "ship", "config", "dest", "arriver", "arrivé", "arrived"})
_QUIT_CMDS   = frozenset({"quit", "exit", "bye", "quitter", "/quit", "/exit", "/bye", "/quitter"})


class OverlayServer:
    """Serveur WebSocket qui expose le moteur CLI au frontend HTML."""

    def __init__(self) -> None:
        self.ctx: AppContext | None = None
        self._clients: set = set()
        self._lock = threading.Lock()
        self._history: list[str] = []

    # ── Initialisation du contexte CLI ────────────────────────────────────────

    def init_context(self) -> None:
        cfg  = _settings.load()
        # Créer le fichier config s'il n'existe pas encore
        if not _settings.CONFIG_PATH.exists():
            try:
                _settings.save(cfg)
                print(f"[overlay] Config créée : {_settings.CONFIG_PATH}", flush=True)
            except Exception as e:
                print(f"[overlay] Impossible de créer la config : {e}", flush=True)
        else:
            print(f"[overlay] Config chargée : {_settings.CONFIG_PATH}", flush=True)
        ttl  = cfg.get("cache", {}).get("ttl_static", 86400)
        cache = CacheManager(ttl_static=ttl)
        try:
            cache.load()
        except Exception:
            pass
        self.ctx = AppContext(cfg=cfg, cache=cache)
        self.ctx.location_index = LocationIndex(cache)
        self.ctx.player = Player.from_config(cfg.get("player", {}))
        self._history = _history_mod.last_n(500)

    # ── Handler WebSocket ─────────────────────────────────────────────────────

    async def handler(self, websocket) -> None:
        self._clients.add(websocket)
        try:
            # Envoyer le statut initial + bannière
            from uexinfo import __version__
            opacity = self.ctx.cfg.get("overlay", {}).get("opacity", 0.76)
            await websocket.send(json.dumps({
                "type":    "banner",
                "text":    f"UEXInfo v{__version__} — /help pour l'aide",
                "opacity": opacity,
            }))
            await self._send_status(websocket)
            await self._send_vocab(websocket)

            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await self._dispatch(websocket, msg)

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)

    async def _dispatch(self, ws, msg: dict) -> None:
        t = msg.get("type")
        if t == "cmd":
            await self._handle_cmd(ws, msg.get("text", "").strip())
        elif t == "complete":
            await self._handle_complete(ws, msg.get("text", ""), msg.get("cursor", -1))
        elif t == "status":
            await self._send_status(ws)
        elif t == "opacity":
            await self._handle_opacity(msg.get("value", 0.76))
        elif t == "cols":
            cols = max(40, int(msg.get("value", 100)))
            _fmt_mod.console._width = cols
        elif t == "scan_confirm":
            await self._handle_scan_confirm(msg.get("data", {}))
        elif t == "history":
            await ws.send(json.dumps({"type": "history", "items": self._history}))

    # ── Exécution des commandes ───────────────────────────────────────────────

    async def _handle_cmd(self, ws, line: str) -> None:
        if not line:
            return

        # Commandes de sortie — tuer le process directement (le plus fiable)
        if line.lower().strip() in _QUIT_CMDS:
            print(f"[overlay] Commande de sortie reçue : {line!r} → os._exit(0)", flush=True)
            try:
                await ws.send(json.dumps({"type": "quit"}))
                await asyncio.sleep(0.15)   # laisser le message partir
            except Exception:
                pass
            os._exit(0)   # tue le process entier, bypasse tout le reste

        # Sauvegarder dans l'historique
        _history_mod.append(line)
        if not self._history or self._history[0] != line:
            self._history.insert(0, line)
            if len(self._history) > 200:
                self._history.pop()

        # Écho
        await ws.send(json.dumps({"type": "echo", "text": line}))

        # Capturer le scan courant avant exécution pour détecter un nouveau scan
        prev_scan = getattr(self.ctx, "last_scan", None)

        # Exécution dans un thread (bloquant)
        loop = asyncio.get_event_loop()
        output, needs_status = await loop.run_in_executor(
            None, self._exec_sync, line
        )

        if output:
            await ws.send(json.dumps({"type": "output", "ansi": output}))

        if needs_status:
            await self._send_status(ws)

        await ws.send(json.dumps({"type": "done"}))

        # Si un nouveau scan vient d'être produit → envoyer les données éditables
        new_scan = getattr(self.ctx, "last_scan", None)
        if new_scan is not None and new_scan is not prev_scan:
            await self._send_scan_edit(ws, new_scan)

        # Après un refresh, le cache change → re-envoyer le vocabulaire
        first = line.strip().lstrip("/").split()[0].lower() if line.strip() else ""
        if first in ("refresh", "r"):
            await self._send_vocab(ws)

    def _exec_sync(self, line: str) -> tuple[str, bool]:
        """Exécute la commande de façon bloquante, retourne (output_ansi, needs_status)."""
        with self._lock:
            _buf.truncate(0)
            _buf.seek(0)

            needs_status = False
            try:
                first = line.strip().lstrip("/").split()[0].lower() if line.strip() else ""

                # Pre-hook scan (identique au CLI)
                if first not in ("scan", "s"):
                    try:
                        from uexinfo.cli.commands.scan import check_log_auto
                        check_log_auto(self.ctx)
                    except Exception:
                        pass

                result = run_command(line, self.ctx)
                needs_status = bool(result & _STATUS_CMDS) if result else False

            except Exception as exc:
                _fmt_mod.console.print(f"[red]✗ Erreur : {exc}[/red]")

            output = _buf.getvalue()
            _buf.truncate(0)
            _buf.seek(0)

        return output.replace("\r\n", "\n").replace("\r", "\n").rstrip(), needs_status

    # ── Opacité ───────────────────────────────────────────────────────────────

    async def _handle_opacity(self, value: float) -> None:
        try:
            v = round(max(0.10, min(0.99, float(value))), 2)
            self.ctx.cfg.setdefault("overlay", {})["opacity"] = v
            _settings.save(self.ctx.cfg)
        except Exception:
            pass

    # ── Statut ────────────────────────────────────────────────────────────────

    async def _send_status(self, ws) -> None:
        if not self.ctx:
            return
        p = self.ctx.player

        cargo = 0
        if p.active_ship:
            for s in p.ships:
                if s.name == p.active_ship:
                    cargo = s.scu or 0
                    break

        dist = None
        if p.location and p.destination and p.location != p.destination:
            try:
                path = self.ctx.cache.transport_graph.shortest_path(
                    p.location, p.destination
                )
                if path and getattr(path, "total_distance", None):
                    dist = round(path.total_distance, 1)
            except Exception:
                pass

        # Détection scans actifs
        scan_sc  = bool(getattr(self.ctx, "last_scan", None))
        scan_log = False
        try:
            import os, time as _t
            log_path = self.ctx.cfg.get("scan", {}).get("sc_log_path", "")
            if log_path and os.path.exists(log_path):
                mtime = os.path.getmtime(log_path)
                last  = getattr(self.ctx, "log_last_mtime", 0) or 0
                scan_log = (mtime > last)
        except Exception:
            pass

        ships = [s.name for s in p.ships] if getattr(p, "ships", None) else []

        await ws.send(json.dumps({
            "type":     "status",
            "pos":      p.location    or "",
            "dest":     p.destination or "",
            "ship":     p.active_ship or "",
            "cargo":    cargo,
            "dist":     dist,
            "scan_sc":  scan_sc,
            "scan_log": scan_log,
            "ships":    ships,
        }))

    # ── Scan éditable ────────────────────────────────────────────────────────

    async def _send_scan_edit(self, ws, result) -> None:
        """Envoie les données d'un ScanResult pour édition dans l'overlay."""
        from uexinfo.models.scan_result import ScanResult
        if not isinstance(result, ScanResult):
            return
        data = {
            "terminal":    result.terminal,
            "mode":        result.mode,
            "source":      result.source,
            "commodities": [
                {
                    "name":         c.name,
                    "commodity_id": c.commodity_id,
                    "price":        c.price,
                    "quantity":     c.quantity,
                    "stock_status": c.stock_status,
                }
                for c in result.commodities
            ],
        }
        await ws.send(json.dumps({"type": "scan_edit", "data": data}))

    async def _handle_scan_confirm(self, data: dict) -> None:
        """Met à jour ctx.last_scan avec les valeurs éditées par l'utilisateur."""
        try:
            result = getattr(self.ctx, "last_scan", None)
            if result is None:
                return
            result.terminal = data.get("terminal", result.terminal)
            result.mode     = data.get("mode",     result.mode)
            for i, cd in enumerate(data.get("commodities", [])):
                if i >= len(result.commodities):
                    break
                c = result.commodities[i]
                c.name         = cd.get("name", c.name)
                c.price        = int(cd.get("price") or 0)
                qty = cd.get("quantity")
                c.quantity     = int(qty) if qty not in (None, "") else None
                c.stock_status = int(cd.get("stock_status") or 0)
            # Re-persister
            from uexinfo.cache.scan_prices import ScanPriceStore
            try:
                ScanPriceStore().save_result(result)
            except Exception:
                pass
        except Exception:
            pass

    # ── Vocabulaire (annotation des termes connus) ────────────────────────────

    async def _send_vocab(self, ws) -> None:
        """Envoie la liste des termes connus pour annotation dans l'output."""
        cache = self.ctx.cache
        MIN = 3  # longueur minimale d'un terme

        commodities = sorted({
            c.name for c in (cache.commodities or [])
            if c.name and len(c.name) >= MIN
        })
        locations = sorted({
            name
            for lst, attr in (
                (cache.star_systems, "name"),
                (cache.planets,      "name"),
                (cache.terminals,    "name"),
            )
            for obj in (lst or [])
            for name in [getattr(obj, attr, None)]
            if name and len(name) >= MIN
        })
        ships = sorted({
            s.name for s in (getattr(self.ctx.player, "ships", None) or [])
            if s.name and len(s.name) >= MIN
        })

        await ws.send(json.dumps({
            "type":        "vocab",
            "commodities": commodities,
            "locations":   locations,
            "ships":       ships,
        }))

    # ── Complétion ────────────────────────────────────────────────────────────

    async def _handle_complete(self, ws, text: str, cursor: int) -> None:
        loop = asyncio.get_event_loop()
        items = await loop.run_in_executor(None, self._complete_sync, text, cursor)
        await ws.send(json.dumps({"type": "completions", "items": items}))

    def _complete_sync(self, text: str, cursor: int) -> list[dict]:
        """Utilise UEXCompleter pour générer les complétions."""
        try:
            from uexinfo.cli.completer import UEXCompleter
            from prompt_toolkit.document import Document
            completer = UEXCompleter(self.ctx)
            cur = cursor if cursor >= 0 else len(text)
            doc = Document(text, cursor_position=cur)
            completions = list(completer.get_completions(doc, None))
            items = []
            for c in completions[:30]:
                # start_position est négatif : nb de chars à remplacer avant le curseur
                prefix = text[:cur + c.start_position]
                value  = prefix + c.text
                hint   = c.display_meta_text or ""
                items.append({"value": value, "hint": hint})
            return items
        except Exception as e:
            print(f"[overlay] complete error: {e}", flush=True)
            return []

    # ── Démarrage ─────────────────────────────────────────────────────────────

    async def serve(self, host: str = "localhost", port: int = 8090) -> None:
        async with websockets.serve(self.handler, host, port):
            await asyncio.Future()  # tourne indéfiniment

    def start_background(self, host: str = "localhost", port: int = 8090) -> None:
        """Lance le serveur WebSocket dans un thread daemon."""
        def _run() -> None:
            asyncio.run(self.serve(host, port))
        t = threading.Thread(target=_run, daemon=True, name="overlay-ws")
        t.start()
