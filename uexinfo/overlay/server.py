"""Serveur WebSocket overlay — reçoit les commandes du frontend HTML et retourne
la sortie Rich structurée (HTML natif) + les mises à jour de statut.

IMPORTANT : ce module doit être importé AVANT tout autre module uexinfo qui
utilise `uexinfo.display.formatter.console`, car il remplace cette console.
"""
from __future__ import annotations

# ── 1. Remplace console AVANT l'import des commandes ─────────────────────────
import uexinfo.display.formatter as _fmt_mod
from uexinfo.display.capturing_console import CapturingConsole as _CapturingConsole

_fmt_mod.console = _CapturingConsole(width=100)

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
import uexinfo.cli.commands.mission      # noqa: F401
import uexinfo.cli.commands.voyage       # noqa: F401
import uexinfo.cli.commands.calc         # noqa: F401
import uexinfo.cli.commands.sync         # noqa: F401
import uexinfo.cli.commands.note         # noqa: F401

from uexinfo.cli.runner import run_command
from uexinfo.cli.context import AppContext
from uexinfo.cache.manager import CacheManager
from uexinfo.cache.mission_manager import MissionManager
from uexinfo.cache.voyage_manager import VoyageManager
from uexinfo.cache.screenshot_db import ScreenshotDB
from uexinfo.location.index import LocationIndex
from uexinfo.models.player import Player
from uexinfo.ocr.ocr_worker import OcrWorker
import uexinfo.config.settings as _settings
import uexinfo.cli.history as _history_mod

_RE_ANSI    = re.compile(r"\x1b\[[0-9;]*[mK]")
_WARN_COLOR = "yellow"
_DIM_COLOR  = "dim"

# Commandes qui nécessitent une mise à jour de la barre de statut
_STATUS_CMDS = frozenset({"player", "p", "go", "lieu", "ship", "config", "dest", "arriver", "arrivé", "arrived",
                          "mission", "m", "voyage", "v", "scan", "s"})
_QUIT_CMDS   = frozenset({"quit", "exit", "bye", "quitter", "/quit", "/exit", "/bye", "/quitter"})


def _clipboard_win(text: str) -> None:
    """Copie text dans le presse-papiers via PowerShell Set-Clipboard (fallback WS)."""
    import sys
    if sys.platform != "win32":
        return
    try:
        import subprocess
        subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-STA",
                "-Command",
                "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
                "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
            ],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as exc:
        print(f"[overlay] clipboard error: {exc}", flush=True)


class OverlayServer:
    """Serveur WebSocket qui expose le moteur CLI au frontend HTML."""

    def __init__(self) -> None:
        self.ctx: AppContext | None = None
        self._clients: set = set()
        self._lock = threading.Lock()
        self._history: list[str] = []
        self.on_quit: callable | None = None  # callback appelé avant os._exit

        # ── Sélecteur interactif ──────────────────────────────────────────────
        # Utilisé pour suspendre _exec_sync en attendant la réponse JS.
        self._select_event  = threading.Event()
        self._select_indices: list[int] | None = None   # None = annulé
        self._loop: asyncio.AbstractEventLoop | None = None

        # ── Screenshot DB + OCR worker ────────────────────────────────────────
        self._screenshot_db: ScreenshotDB | None = None
        self._ocr_worker:    OcrWorker    | None = None

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
        # Migration clés terminaux → str(id) dans scan_prices.json
        try:
            from uexinfo.cache.scan_prices import ScanPriceStore
            n = ScanPriceStore().migrate_keys(self.ctx)
            if n:
                print(f"[overlay] scan_prices: {n} clé(s) terminal migrée(s) → ID", flush=True)
        except Exception as _e:
            print(f"[overlay] scan_prices migration: {_e}", flush=True)
        self.ctx.mission_manager = MissionManager()
        retention = self.ctx.cfg.get("voyages", {}).get("retention", 24)
        self.ctx.voyage_manager = VoyageManager(retention=retention)
        self._history = _history_mod.last_n(500)

        # ── Screenshot DB + OCR worker ────────────────────────────────────────
        self._screenshot_db = ScreenshotDB()
        self._ocr_worker    = OcrWorker(self._screenshot_db, self.ctx)
        self._ocr_worker.set_gap_minutes(
            self.ctx.cfg.get("scan", {}).get("session_gap", 60)
        )
        self._ocr_worker.on_processed(self._on_screenshot_processed)
        # Exposer la DB dans le contexte pour les commandes CLI
        self.ctx.screenshot_db = self._screenshot_db

    # ── Handler WebSocket ─────────────────────────────────────────────────────

    async def handler(self, websocket) -> None:
        self._clients.add(websocket)
        _current_cmd: asyncio.Task | None = None
        _recv_task:   asyncio.Task | None = None
        _queued_cmd:  dict | None = None   # 1 commande en attente si occupé

        try:
            # Séquence d'initialisation : status → vocab → history → blocs écho → banner
            # Le banner est envoyé EN DERNIER pour appliquer l'opacité
            # seulement une fois le contenu chargé (évite le flash opaque au démarrage).
            from uexinfo import __version__
            ov_cfg     = self.ctx.cfg.get("overlay", {})
            opacity    = ov_cfg.get("opacity", 0.76)
            close_mode = ov_cfg.get("close", "normal")
            clock      = ov_cfg.get("clock", True)

            await self._send_status(websocket)
            await self._send_vocab(websocket)

            # Envoyer l'historique de saisie (navigation ↑/↓)
            await websocket.send(json.dumps({"type": "history", "items": self._history}))

            # Afficher les N dernières commandes avec leurs résultats stockés (sans ré-exécution)
            cmdhistory_n = ov_cfg.get("cmdhistory", 5)
            # last_n_raw_with_output : plus récentes en premier → on inverse pour afficher du plus ancien au plus récent
            recent = list(reversed(_history_mod.last_n_raw_with_output(cmdhistory_n)))
            for entry in recent:
                await websocket.send(json.dumps({"type": "echo", "text": entry["cmd"]}))
                if entry["html"]:
                    await websocket.send(json.dumps({"type": "output_html", "html": entry["html"]}))
                await websocket.send(json.dumps({"type": "done"}))

            # Banner EN DERNIER → déclenche setAlpha → overlay devient visible
            await websocket.send(json.dumps({
                "type":       "banner",
                "text":       f"UEXInfo v{__version__} — /help pour l'aide",
                "opacity":    opacity,
                "close_mode": close_mode,
                "clock":      clock,
            }))

            # Boucle principale : asyncio.wait permet de traiter "cancel"
            # pendant qu'une commande longue est en cours dans un thread.
            _recv_task = asyncio.create_task(websocket.recv())

            while True:
                waiters: set[asyncio.Task] = {_recv_task}
                if _current_cmd and not _current_cmd.done():
                    waiters.add(_current_cmd)

                done, _ = await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)

                # Commande terminée naturellement → exécuter la commande en attente si présente
                if _current_cmd in done:
                    _current_cmd = None
                    if _queued_cmd is not None:
                        _msg_to_run, _queued_cmd = _queued_cmd, None
                        self.ctx._cancel_flag.clear()
                        _current_cmd = asyncio.create_task(self._dispatch(websocket, _msg_to_run))

                # Pas de nouveau message — attendre la prochaine itération
                if _recv_task not in done:
                    continue

                # Nouveau message WebSocket
                try:
                    raw = _recv_task.result()
                except Exception:
                    break   # connexion fermée
                _recv_task = asyncio.create_task(websocket.recv())

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                t = msg.get("type")

                # ── Réponse au sélecteur (toujours prioritaire) ───────────
                if t in ("select_confirm", "select_cancel"):
                    if t == "select_confirm":
                        self._select_indices = msg.get("indices", [])
                    else:
                        self._select_indices = None
                    self._select_event.set()
                    continue

                # ── Annulation (double-Esc) ────────────────────────────────
                if t == "cancel":
                    _queued_cmd = None   # vider la file d'attente aussi
                    if _current_cmd and not _current_cmd.done():
                        self.ctx._cancel_flag.set()
                        _current_cmd.cancel()
                        try:
                            await asyncio.wait_for(
                                asyncio.shield(_current_cmd), timeout=2.0
                            )
                        except (asyncio.CancelledError, asyncio.TimeoutError):
                            pass
                        _current_cmd = None
                        import io as _io2
                        _cbuf = _io2.StringIO()
                        from rich.console import Console as _RC
                        _rc = _RC(file=_cbuf, force_terminal=True, markup=True,
                                  highlight=False, width=100)
                        _rc.print("\n[bold yellow]⚠ Commande annulée (Échap×2)[/bold yellow]")
                        await websocket.send(json.dumps({
                            "type": "output",
                            "ansi": _cbuf.getvalue(),
                        }))
                        await websocket.send(json.dumps({"type": "done"}))
                    self.ctx._cancel_flag.clear()

                # ── Nouvelle commande ──────────────────────────────────────
                elif _current_cmd is None or _current_cmd.done():
                    self.ctx._cancel_flag.clear()
                    _current_cmd = asyncio.create_task(self._dispatch(websocket, msg))
                elif msg.get("type") == "cmd":
                    # Commande en cours : mettre en file d'attente (remplace la précédente)
                    _queued_cmd = msg

        except websockets.exceptions.ConnectionClosed:
            if _current_cmd:
                _current_cmd.cancel()
        finally:
            self._clients.discard(websocket)
            if _recv_task and not _recv_task.done():
                _recv_task.cancel()

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
            await self._handle_scan_confirm(ws, msg.get("data", {}))
        elif t == "scan_existing_save":
            await self._handle_scan_existing_save(ws, msg.get("data", {}))
        elif t == "trade_chosen":
            await self._handle_trade_chosen(msg.get("idx"))
        elif t == "terminal_buy_chosen":
            await self._handle_terminal_buy_chosen(ws, msg.get("data", {}))
        elif t == "mission_scan_confirm":
            await self._handle_mission_scan_confirm(ws, msg.get("data", {}))
        elif t == "mission_edit_confirm":
            await self._handle_mission_edit_confirm(ws, msg.get("data", {}))
        elif t == "mission_list_reload":
            # Recharger la liste après suppression/modification
            output, _ = await asyncio.get_event_loop().run_in_executor(
                None, self._exec_sync, "/mission list"
            )
            await ws.send(json.dumps({"type": "done"}))
            await self._send_status(ws)
        elif t == "open_file":
            path = msg.get("path", "")
            if path:
                import os, subprocess, sys
                from pathlib import Path as _Path
                try:
                    abs_path = str(_Path(path).resolve())
                    print(f"[overlay] open_file: {abs_path}", flush=True)
                    if sys.platform == "win32":
                        os.startfile(abs_path)
                    elif sys.platform == "darwin":
                        subprocess.Popen(["open", abs_path])
                    else:
                        subprocess.Popen(["xdg-open", abs_path])
                except Exception as e:
                    print(f"[overlay] open_file error: {e}", flush=True)
        elif t == "history":
            await ws.send(json.dumps({"type": "history", "items": self._history}))
        elif t == "copy":
            _clipboard_win(msg.get("text", ""))

    # ── Exécution des commandes ───────────────────────────────────────────────

    async def _handle_cmd(self, ws, line: str) -> None:
        if not line:
            return

        # Commandes de sortie — tuer le process directement (le plus fiable)
        _parts = line.lower().strip().split()
        _tbc = "-tbc" in _parts
        if _parts and _parts[0] in _QUIT_CMDS:
            print(f"[overlay] Commande de sortie reçue : {line!r} → os._exit(0)", flush=True)
            try:
                await ws.send(json.dumps({"type": "quit"}))
                await asyncio.sleep(0.15)   # laisser le message partir
            except Exception:
                pass
            if self.on_quit:
                self.on_quit(tbc=_tbc)    # lance _shutdown dans un thread → os._exit(0)
                await asyncio.sleep(2)    # attendre le os._exit(0) du thread
            os._exit(0)  # fallback au cas où on_quit ne tue pas

        # Mémoriser la commande originale (avant résolution des abréviations)
        original_line = line

        # Mise à jour de l'historique en mémoire (navigation ↑/↓)
        if not self._history or self._history[0] != line:
            self._history.insert(0, line)
            if len(self._history) > 500:
                self._history.pop()

        # Résoudre les abréviations *-suffixées (noms de lieux) dans la commande
        from uexinfo.display.loc import resolve_cmd_line as _resolve_loc
        line = _resolve_loc(line)

        # Écho
        await ws.send(json.dumps({"type": "echo", "text": line}))

        # Capturer la longueur de l'historique AVANT exec pour détecter les nouveaux scans
        prev_history_len = len(getattr(self.ctx, "scan_history", []))
        # Capturer l'id de last_trade_entries / last_terminal_buy_entries pour détecter une mise à jour
        prev_trade_id = id(getattr(self.ctx, "last_trade_entries", None))
        prev_tbuy_id  = id(getattr(self.ctx, "last_terminal_buy_entries", None))

        # Injecter select_fn pour ce websocket (permet aux commandes d'ouvrir
        # le sélecteur overlay au lieu du TUI terminal)
        self.ctx.select_fn = lambda items, title="", mode="multi", confirm_label="": \
            self._overlay_select_sync(ws, items, title, mode, confirm_label)

        # Injecter _overlay_send_fn : permet à /mission scan d'envoyer mission_scan_list
        _send_q: list[dict] = []
        self.ctx._overlay_send_fn = _send_q.append

        # Exécution dans un thread (bloquant) + streaming de progression
        loop = asyncio.get_event_loop()

        # Injecter _overlay_progress_fn : mise à jour de progression en place (thread-safe)
        def _sync_progress(pct: int, label: str, done: int, total: int) -> None:
            asyncio.run_coroutine_threadsafe(
                ws.send(json.dumps({
                    "type": "progress_update",
                    "pct": pct, "label": label,
                    "done": done, "total": total,
                })),
                loop,
            )
        self.ctx._overlay_progress_fn = _sync_progress

        try:
            output, needs_status = await loop.run_in_executor(
                None, self._exec_sync, line
            )
        except asyncio.CancelledError:
            raise

        # Générer HTML depuis les renderables capturés (ou fallback ANSI→HTML)
        from uexinfo.display.render_html import rich_renderables_to_html as _r2h
        renderables = _fmt_mod.console.flush_renderables()
        if renderables:
            html_output = _r2h(renderables)
        else:
            from uexinfo.display.ansi_html import ansi_to_html as _ansi_to_html
            html_output = _ansi_to_html(output)

        # Sauvegarder la commande + son output HTML dans l'historique persistant
        _history_mod.append(original_line, html_output=html_output)

        self.ctx.select_fn = None
        self.ctx._overlay_send_fn = None
        self.ctx._overlay_progress_fn = None
        await ws.send(json.dumps({"type": "progress_done"}))

        # Envoyer les abréviations de lieux AVANT l'output (le JS les aura quand il annote)
        from uexinfo.display.loc import flush_abbrevs as _flush_loc
        _loc_map = _flush_loc()
        if _loc_map:
            await ws.send(json.dumps({"type": "loc_abbrevs", "map": _loc_map}))

        # Messages "pré-output" : formulaires qui remplacent l'output (scan_log_inline)
        # Messages "post-output" : boutons/actions inline qui suivent le tableau (tout le reste)
        pre_types  = {"scan_log_inline"}
        pre_msgs   = [m for m in _send_q if m.get("type") in pre_types]
        post_msgs  = [m for m in _send_q if m.get("type") not in pre_types]

        for msg in pre_msgs:
            await ws.send(json.dumps(msg))

        # Pour /scan log, le formulaire inline remplace l'output texte
        is_scan_log = line.strip().lstrip("/").lower().startswith("scan log")
        if html_output and not is_scan_log:
            await ws.send(json.dumps({"type": "output_html", "html": html_output}))

        # Messages post-output : boutons d'action inline (mission_actions_inline, voyage_calc_result…)
        for msg in post_msgs:
            await ws.send(json.dumps(msg))

        if needs_status:
            await self._send_status(ws)

        await ws.send(json.dumps({"type": "done"}))

        # Envoyer un éditeur pour chaque nouveau ScanResult (tous les types de scan)
        new_scans = getattr(self.ctx, "scan_history", [])[prev_history_len:]
        for result in new_scans:
            await self._send_scan_edit(ws, result)

        # Envoyer trade_pick si les résultats trade ont changé
        new_trade = getattr(self.ctx, "last_trade_entries", None)
        if new_trade is not None and id(new_trade) != prev_trade_id:
            await ws.send(json.dumps({"type": "trade_pick", **new_trade}))

        # Envoyer terminal_buy_pick si les entrées d'achat terminal ont changé
        new_tbuy = getattr(self.ctx, "last_terminal_buy_entries", None)
        if new_tbuy is not None and id(new_tbuy) != prev_tbuy_id:
            await ws.send(json.dumps({"type": "terminal_buy_pick", **new_tbuy}))

        # Envoyer les messages overlay mis en file par les commandes
        pending = getattr(self.ctx, "_overlay_msgs", [])
        for msg in pending:
            await ws.send(json.dumps(msg))
        self.ctx._overlay_msgs = []

        # Après un refresh, le cache change → re-envoyer le vocabulaire
        first = line.strip().lstrip("/").split()[0].lower() if line.strip() else ""
        if first in ("refresh", "r", "voyage", "v", "mission", "m"):
            await self._send_vocab(ws)

    def _exec_sync(self, line: str) -> tuple[str, bool]:
        """Exécute la commande de façon bloquante, retourne (output_ansi_fallback, needs_status).

        Le rendu principal passe maintenant par CapturingConsole._renderables → HTML natif.
        L'ANSI est conservé en fallback (commandes non migrées, annulation, etc.).
        """
        _fmt_mod.console.reset_capture()

        needs_status = False
        try:
            result = run_command(line, self.ctx)
            needs_status = bool(result & _STATUS_CMDS) if result else False
        except Exception as exc:
            from rich.markup import escape as _esc
            _fmt_mod.console.print(f"[red]✗ Erreur : {_esc(str(exc))}[/red]")

        output = _fmt_mod.console.flush_ansi()
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
                path = self.ctx.cache.transport_graph.find_shortest_path(
                    p.location, p.destination
                )
                if path is not None and path.total_distance is not None:
                    dist = round(path.total_distance, 1)
            except Exception:
                pass

        # Détection scans actifs
        import os as _os, time as _t
        # scan_log : le fichier log a-t-il changé depuis la dernière lecture ?
        scan_log = False
        try:
            log_path = self.ctx.cfg.get("scan", {}).get("sc_log_path", "")
            if log_path and _os.path.exists(log_path):
                mtime = _os.path.getmtime(log_path)
                last  = getattr(self.ctx, "log_last_mtime", 0) or 0
                scan_log = (mtime > last)
        except Exception:
            pass

        # scan_sc : y a-t-il de nouveaux screenshots depuis le dernier scan ?
        scan_sc = False
        try:
            from uexinfo.cli.commands.scan import _screenshots_dir, _IMAGE_SUFFIXES
            sc_dir  = _screenshots_dir(self.ctx)
            last_ts = getattr(self.ctx, "screenshots_last_seen_ts", 0.0) or 0.0
            if sc_dir.is_dir():
                if last_ts == 0.0:
                    # Première fois : initialiser sans signaler
                    self.ctx.screenshots_last_seen_ts = _t.time()
                else:
                    scan_sc = any(
                        p.stat().st_mtime > last_ts
                        for p in sc_dir.iterdir()
                        if p.suffix.lower() in _IMAGE_SUFFIXES
                    )
        except Exception:
            pass

        ships = [s.name for s in p.ships] if getattr(p, "ships", None) else []

        vm = getattr(self.ctx, "voyage_manager", None)
        active_voyage = vm.get_active() if vm else None
        voyage_name   = active_voyage.name if active_voyage else ""
        voyage_count  = len(active_voyage.mission_ids) if active_voyage else 0

        await ws.send(json.dumps({
            "type":          "status",
            "pos":           p.location    or "",
            "dest":          p.destination or "",
            "ship":          p.active_ship or "",
            "cargo":         cargo,
            "dist":          dist,
            "voyage_name":  voyage_name,
            "voyage_count": voyage_count,
            # ScanLog a la priorité : ScanSC ne clignote pas quand ScanLog est en attente
            "scan_sc":  scan_sc and not scan_log,
            "scan_log": scan_log,
            "ships":    ships,
        }))

    # ── Scan éditable ────────────────────────────────────────────────────────

    async def _send_scan_edit(self, ws, result) -> None:
        """Envoie les données d'un ScanResult pour édition dans l'overlay."""
        from uexinfo.models.scan_result import ScanResult
        if not isinstance(result, ScanResult):
            return

        # Encoder le crop de la région commodités en base64 (scans OCR uniquement)
        # Crop = (58%, 12%, 100%, 100%) — identique aux constantes de engine.py
        image_b64 = ""
        if result.image_path:
            try:
                import base64, io as _bio
                from pathlib import Path
                from PIL import Image as _PILImage
                img_path = Path(result.image_path)
                if img_path.is_file() and img_path.stat().st_size < 5 * 1024 * 1024:
                    _img = _PILImage.open(img_path)
                    _w, _h = _img.size
                    _crop = _img.crop((int(_w * 0.58), int(_h * 0.12), _w, _h))
                    _buf = _bio.BytesIO()
                    _crop.save(_buf, format="JPEG", quality=80)
                    image_b64 = "data:image/jpeg;base64," + base64.b64encode(_buf.getvalue()).decode()
            except Exception:
                pass

        # Récupérer les prix UEX de référence pour détection d'anomalies
        uex_ref = {}  # commodity_name.lower() → {"price_buy": N, "price_sell": N}
        try:
            cache = getattr(self.ctx, "cache", None)
            if cache:
                for comm in (cache.commodities or []):
                    uex_ref[comm.name.lower()] = {
                        "price_buy": comm.price_buy or 0,
                        "price_sell": comm.price_sell or 0,
                    }
        except Exception:
            pass

        is_sell = result.mode == "sell"
        ref_field = "price_sell" if is_sell else "price_buy"

        # Filtrer les commodités OCR noise : nom inconnu UEX + prix nul
        known_names = set(uex_ref.keys())
        def _keep(c):
            name_lc = c.name.lower().strip()
            if not name_lc:
                return False
            in_uex = name_lc in known_names or c.commodity_id > 0
            # Garder si : nom reconnu UEX, OU prix non nul (joueur a un prix même si nom OCR imparfait)
            return in_uex or c.price > 0

        commodities_filtered = [c for c in result.commodities if _keep(c)]

        data = {
            "terminal":    result.terminal,
            "mode":        result.mode,
            "source":      result.source,
            "validated":   result.validated,
            "image_b64":   image_b64,
            "commodities": [
                {
                    "name":         c.name,
                    "commodity_id": c.commodity_id,
                    "price":        c.price,
                    "quantity":     c.quantity,
                    "stock_status": c.stock_status,
                    "uex_price":    uex_ref.get(c.name.lower(), {}).get(ref_field, 0),
                }
                for c in commodities_filtered
            ],
        }
        # Scans log validés → formulaire inline dans l'output (pas de panel plein-écran)
        msg_type = "scan_log_inline"  # toujours inline, plus de popup modal
        await ws.send(json.dumps({"type": msg_type, "data": data}))

    async def _handle_scan_confirm(self, ws, data: dict) -> None:
        """Met à jour le ScanResult correspondant avec les valeurs éditées et persiste."""
        try:
            from uexinfo.models.scan_result import ScannedCommodity
            # Pour les scans inline (log), trouver le bon résultat par terminal+mode
            raw_terminal = (data.get("terminal") or "").strip()
            # Stripper le suffixe système "(Stanton)" ajouté pour désambiguïser
            import re as _re
            terminal_bare = _re.sub(r'\s*\([^)]+\)$', '', raw_terminal).strip()
            terminal_key  = terminal_bare.lower()
            mode_key     = data.get("mode") or ""
            result       = None
            if terminal_key and mode_key:
                history = getattr(self.ctx, "scan_history", [])
                for r in reversed(history):
                    if r.terminal.lower() == terminal_key and r.mode == mode_key:
                        result = r
                        break
            if result is None:
                result = getattr(self.ctx, "last_scan", None)
            if result is None:
                return
            result.terminal = terminal_bare or result.terminal
            result.mode     = data.get("mode", result.mode)

            incoming = data.get("commodities", [])
            single_idx = data.get("single_idx")   # None = tout, int = une seule ligne

            if single_idx is not None:
                # MàJ d'une seule ligne par nom (l'index côté JS peut avoir changé)
                cd = incoming[single_idx] if single_idx < len(incoming) else None
                if cd:
                    name_q = (cd.get("name") or "").lower()
                    # Chercher par nom dans le résultat existant
                    target = next((c for c in result.commodities if c.name.lower() == name_q), None)
                    if target:
                        target.name         = cd.get("name", target.name)
                        target.price        = int(cd.get("price") or 0)
                        qty = cd.get("quantity")
                        target.quantity     = int(qty) if qty not in (None, "") else None
                        target.stock_status = int(cd.get("stock_status") or 0)
                    else:
                        # Nouvelle commodité ajoutée par l'utilisateur
                        result.commodities.append(self._make_scanned_commodity(cd))
            else:
                # Valider tout : reconstruire la liste complète depuis les données reçues
                # Conserver les commodity_id des entrées existantes (match par nom)
                old_by_name = {c.name.lower(): c for c in result.commodities}
                new_comms = []
                for cd in incoming:
                    name = cd.get("name") or ""
                    if not name:
                        continue
                    old = old_by_name.get(name.lower())
                    sc = ScannedCommodity(
                        name=name,
                        commodity_id=old.commodity_id if old else 0,
                        price=int(cd.get("price") or 0),
                        quantity=int(cd["quantity"]) if cd.get("quantity") not in (None, "") else None,
                        stock_status=int(cd.get("stock_status") or 0),
                    )
                    new_comms.append(sc)
                result.commodities = new_comms

            # Résoudre les commodity_ids manquants via le cache UEX
            comm_name_to_id: dict[str, int] = {
                c.name.lower(): c.id
                for c in (getattr(self.ctx.cache, "commodities", None) or [])
                if c.id
            }
            for sc in result.commodities:
                if not sc.commodity_id:
                    found = comm_name_to_id.get(sc.name.lower().strip())
                    if found:
                        sc.commodity_id = found

            # Persister
            from uexinfo.cache.scan_prices import ScanPriceStore
            store = ScanPriceStore()
            # Migrer les anciennes clés name:xxx vers id-based si l'id est maintenant connu
            data = store._load()
            term_key = result.terminal.lower().strip()
            if term_key in data:
                term = data[term_key]
                to_migrate = [(k, v) for k, v in list(term.items()) if k.startswith("name:")]
                changed = False
                for old_key, entry in to_migrate:
                    cname = old_key[5:]  # strip "name:"
                    new_id = comm_name_to_id.get(cname)
                    if new_id:
                        new_key = str(new_id)
                        # Fusionner : garder la plus récente
                        existing = term.get(new_key)
                        if not existing or entry.get("timestamp", 0) >= existing.get("timestamp", 0):
                            entry["commodity_id"] = new_id
                            term[new_key] = entry
                        del term[old_key]
                        changed = True
                if changed:
                    data[term_key] = term
                    store._write(data)
            from uexinfo.cli.commands.scan import _terminal_store_key
            term_key_canonical = _terminal_store_key(result.terminal, self.ctx)
            store.save_result(result, terminal_key=term_key_canonical)
        except Exception:
            return

        # Confirmer la sauvegarde sans re-parser le log (évite doublon + saut de formulaire)
        try:
            await ws.send(json.dumps({"type": "done"}))
            await self._send_status(ws)
        except Exception:
            pass

    # ── Trade pick (choisir un trade → mission) ───────────────────────────────

    async def _handle_trade_chosen(self, idx) -> None:
        """Crée une mission simple à partir de la ligne de trade choisie."""
        entries_data = getattr(self.ctx, "last_trade_entries", None)
        if not entries_data:
            return
        try:
            entry = next((e for e in entries_data["entries"] if e["idx"] == idx), None)
            if not entry:
                return
            from uexinfo.models.mission import Mission, MissionObjective
            obj = MissionObjective(
                commodity=entry["name"],
                source=entries_data["origin"],
                destination=entries_data["dest"],
                quantity_scu=float(entry["qty"]) if entry.get("qty") else None,
            )
            name = f'{entry["name"]} {entries_data["origin"]}→{entries_data["dest"]}'
            mission = Mission(
                id=0,
                name=name[:45],
                reward_uec=int(entry["profit"]),
                objectives=[obj],
                source_raw="trade",
            )
            mm = getattr(self.ctx, "mission_manager", None)
            if mm:
                mm.add(mission)
                print(f"[overlay] Mission créée : {mission.name}", flush=True)
        except Exception as e:
            print(f"[overlay] trade_chosen error: {e}", flush=True)

    async def _handle_scan_existing_save(self, ws, data: dict) -> None:
        """Sauvegarde les modifications d'un formulaire scan_edit_existing."""
        try:
            from uexinfo.cache.scan_prices import ScanPriceStore
            store = ScanPriceStore()
            term_key = data.get("terminal") or ""
            rows = data.get("commodities") or []
            if not term_key:
                return

            # Construire le nouveau contenu du terminal
            raw = store._load()
            term_data: dict = {}
            for row in rows:
                cid_key  = row.get("cid_key") or ""
                name     = row.get("name") or ""
                mode     = row.get("mode") or "buy"
                price    = int(row.get("price") or 0)
                stock    = int(row.get("stock_status") or 0)
                qty      = row.get("quantity")
                # Récupérer l'entrée existante (même cid_key) ou en créer une
                stored_tk = row.get("stored_tk") or term_key
                existing  = (raw.get(stored_tk) or {}).get(cid_key, {}) if stored_tk in raw else {}
                entry     = dict(existing)
                entry["commodity_name"] = name
                # Résoudre commodity_id depuis le cache
                comm_name_to_id = {
                    c.name.lower(): c.id
                    for c in (getattr(self.ctx.cache, "commodities", None) or [])
                    if c.id
                }
                cid = existing.get("commodity_id") or comm_name_to_id.get(name.lower(), 0)
                entry["commodity_id"] = cid
                import time as _t
                entry["timestamp"] = _t.time()
                entry["validated"] = True
                if mode == "buy":
                    entry["price_buy"]   = price
                    entry["status_buy"]  = stock
                    if qty is not None:
                        entry["scu_buy"] = int(qty)
                    # Retirer l'ancien côté sell si ce n'est pas dans les données
                else:
                    entry["price_sell"]    = price
                    entry["status_sell"]   = stock
                    if qty is not None:
                        entry["scu_sell_stock"] = int(qty)
                        existing_max = entry.get("scu_sell_max") or 0
                        if int(qty) > existing_max:
                            entry["scu_sell_max"] = int(qty)

                final_key = str(cid) if cid else (cid_key or f"name:{name.lower()}")
                term_data[final_key] = entry

            # Remplacer TOUTES les entrées du terminal (toutes les clés candidates)
            for tk in list(raw.keys()):
                if tk == term_key or tk.replace(" ", "_") == term_key or term_key.replace("_", " ") == tk:
                    del raw[tk]
            raw[term_key] = term_data
            store._write(raw)

            # Invalider le cache prix pour ce terminal
            for k in list(getattr(self.ctx, "_price_cache", {}).keys()):
                if "tn_" in k or k.startswith("t"):
                    pass  # laisser — les données terminal viennent de l'API

            await ws.send(json.dumps({"type": "done"}))
            await self._send_status(ws)
        except Exception as e:
            print(f"[overlay] scan_existing_save error: {e}", flush=True)

    async def _handle_terminal_buy_chosen(self, ws, data: dict) -> None:
        """Crée une mission à partir d'une ligne Acheter sur place (terminal view)."""
        try:
            entries_data = getattr(self.ctx, "last_terminal_buy_entries", None)
            if not entries_data:
                return
            idx = data.get("idx", -1)
            qty = data.get("qty")
            entry = next((e for e in entries_data["entries"] if e["idx"] == idx), None)
            if not entry:
                return

            scu = int(qty) if qty else entry["qty"]
            profit = int((entry["price_sell"] - entry["price_buy"]) * scu)

            from uexinfo.models.mission import Mission, MissionObjective
            obj = MissionObjective(
                commodity=entry["name"],
                source=entries_data["origin"],
                destination=entry["dest"],
                quantity_scu=float(scu),
            )
            name = f'{entry["name"]} {entries_data["origin"]}→{entry["dest"]}'
            mission = Mission(
                id=0,
                name=name[:45],
                reward_uec=profit,
                objectives=[obj],
                source_raw="trade",
            )
            mm = getattr(self.ctx, "mission_manager", None)
            if mm:
                mm.add(mission)
                print(f"[overlay] Mission créée : {mission.name} ({scu} SCU, profit {profit})", flush=True)
                await self._send_status(ws)
        except Exception as e:
            print(f"[overlay] terminal_buy_chosen error: {e}", flush=True)

    # ── Mission edit confirm ───────────────────────────────────────────────────

    async def _handle_mission_edit_confirm(self, ws, data: dict) -> None:
        """Applique les modifications de missions envoyées par le formulaire overlay."""
        from uexinfo.models.mission import MissionObjective
        mm = self.ctx.mission_manager
        updated: list[int] = []

        for mdata in data.get("missions", []):
            mid = mdata.get("id")
            m = mm.get(str(mid))
            if not m:
                continue

            name = (mdata.get("name") or "").strip()
            if name:
                m.name = name

            try:
                r = int(str(mdata.get("reward") or "").replace(",", "").replace(" ", "") or "0")
                if r > 0:
                    m.reward_uec = r
            except (ValueError, TypeError):
                pass

            total_scu: float | None = None
            try:
                scu_raw = str(mdata.get("scu") or "").replace(",", ".").strip()
                if scu_raw:
                    total_scu = float(scu_raw)
            except (ValueError, TypeError):
                pass

            srcs = [s.strip() for s in mdata.get("sources", []) if s.strip()]
            dsts = [d.strip() for d in mdata.get("destinations", []) if d.strip()]

            if srcs or dsts:
                existing_commodity = next(
                    (o.commodity for o in m.objectives if o.commodity), None
                )
                n = max(len(srcs), len(dsts), 1)
                objs: list[MissionObjective] = []
                for k in range(n):
                    src = srcs[k] if k < len(srcs) else None
                    dst = dsts[k] if k < len(dsts) else None
                    qty = total_scu if k == 0 else None
                    objs.append(MissionObjective(
                        commodity=existing_commodity, source=src,
                        destination=dst, quantity_scu=qty,
                    ))
                m.objectives = objs
            elif total_scu is not None and m.objectives:
                m.objectives[0].quantity_scu = total_scu

            mm.update(m)
            updated.append(mid)

        if updated:
            ids_str = ", ".join(f"#{i}" for i in updated)
            await ws.send(json.dumps({
                "type": "output",
                "ansi": f"\x1b[32m✓ {len(updated)} mission(s) modifiée(s) : {ids_str}\x1b[0m\n",
            }))
        await ws.send(json.dumps({"type": "done"}))
        await self._send_status(ws)

    # ── Mission scan — sélection overlay ─────────────────────────────────────

    async def _handle_mission_scan_confirm(self, ws, data: dict) -> None:
        """Ajoute les missions sélectionnées au catalogue (et au voyage si demandé)."""
        files        = data.get("files", [])
        add_to_voyage = data.get("add_to_voyage", False)

        if not files or not self._screenshot_db:
            await ws.send(json.dumps({"type": "done"}))
            return

        loop = asyncio.get_event_loop()
        output, _ = await loop.run_in_executor(
            None, self._exec_mission_scan_add, files, add_to_voyage
        )

        if output:
            await ws.send(json.dumps({"type": "output", "ansi": output}))
        await ws.send(json.dumps({"type": "done"}))
        await self._send_status(ws)

    def _exec_mission_scan_add(self, files: list[str], add_to_voyage: bool) -> tuple[str, bool]:
        """Exécute l'ajout des missions sélectionnées (thread bloquant)."""
        with self._lock:
            _fmt_mod.console.reset_capture()
            try:
                from uexinfo.cache.mission_scan import entry_to_mission_result, source_raw_from_entry
                from uexinfo.models.mission import Mission

                entries = [
                    self._screenshot_db.get(f)
                    for f in files
                    if self._screenshot_db.has(f)
                ]
                entries = [e for e in entries if e and e.is_mission]

                if not entries:
                    _fmt_mod.console.print(f"[{_WARN_COLOR}]⚠ Aucune mission valide sélectionnée[/{_WARN_COLOR}]")
                else:
                    mm = self.ctx.mission_manager
                    vm = self.ctx.voyage_manager
                    active = vm.get_active() if add_to_voyage else None
                    added  = 0
                    for e in entries:
                        mr = entry_to_mission_result(e)
                        if mr is None:
                            continue
                        kwargs = mr.to_mission_kwargs()
                        kwargs["source_raw"] = source_raw_from_entry(e)
                        kwargs["scanned_at"] = e.file_mtime
                        m = Mission(id=0, **kwargs)
                        mm.add(m)
                        added += 1
                        _fmt_mod.console.print(
                            f"  [green]✓[/green] [bold]#{m.id}[/bold] {m.name}"
                            f"  [{_DIM_COLOR}]{m.reward_uec:,} aUEC[/{_DIM_COLOR}]"
                        )
                        if active:
                            active.mission_ids.append(m.id)
                    if active and added:
                        vm.update(active)
                        _fmt_mod.console.print(
                            f"[green]✓ {added} mission(s) ajoutée(s) au catalogue "
                            f"et au voyage « {active.name} »[/green]"
                        )
                    elif added:
                        _fmt_mod.console.print(f"[green]✓ {added} mission(s) ajoutée(s) au catalogue[/green]")

            except Exception as exc:
                _fmt_mod.console.print(f"[red]✗ Erreur : {exc}[/red]")

            output = _fmt_mod.console.flush_ansi()
        return output.replace("\r\n", "\n").replace("\r", "\n").rstrip(), True

    # ── Vocabulaire (annotation des termes connus) ────────────────────────────

    async def _send_vocab(self, ws) -> None:
        """Envoie la liste des termes connus pour annotation dans l'output."""
        cache = self.ctx.cache
        MIN = 3  # longueur minimale d'un terme

        def _loc(full_name: str) -> str:
            """Retire le préfixe service ('Admin - ', 'Shop - ', …)."""
            return full_name.rsplit(" - ", 1)[-1].strip()

        # Noms depuis la liste statique UEX + cache de prix API + scans joueur
        # (couvre les items saisonniers: "Year of the Rat Envelope", "Audio Visual Equipment"…)
        _price_cache = getattr(self.ctx, "_price_cache", None)
        _extra_comms: set[str] = set()
        if _price_cache is not None:
            for _entry in getattr(_price_cache, "_mem", {}).values():
                _data = _entry.get("data", [])
                if not isinstance(_data, list):
                    continue   # rd_* distances, cs_* containers, etc. — pas des listes de prix
                for _row in _data:
                    if not isinstance(_row, dict):
                        continue
                    _cn = _row.get("commodity_name")
                    if _cn and len(_cn) >= MIN:
                        _extra_comms.add(_cn)
        try:
            from uexinfo.cache.scan_prices import ScanPriceStore as _SPS
            for _term_data in _SPS()._load().values():
                for _entry in _term_data.values():
                    _cn = _entry.get("commodity_name")
                    if _cn and len(_cn) >= MIN:
                        _extra_comms.add(_cn)
        except Exception:
            pass
        commodities = sorted({
            c.name for c in (cache.commodities or [])
            if c.name and len(c.name) >= MIN
        } | _extra_comms)
        locations = sorted({
            name_variant
            for lst, attr in (
                (cache.star_systems, "name"),
                (cache.planets,      "name"),
                (cache.terminals,    "name"),
            )
            for obj in (lst or [])
            for raw in [getattr(obj, attr, None)]
            if raw and len(raw) >= MIN
            for name_variant in (
                # Pour les terminaux : émettre aussi le nom court (sans préfixe service)
                ([raw, _loc(raw)] if lst is cache.terminals else [raw])
            )
            if name_variant and len(name_variant) >= MIN
        })
        ships = sorted({
            s.name for s in (getattr(self.ctx.player, "ships", None) or [])
            if s.name and len(s.name) >= MIN
        })
        vm = getattr(self.ctx, "voyage_manager", None)
        voyages = sorted(vm.voyage_names()) if vm else []

        cmdhistory = self.ctx.cfg.get("overlay", {}).get("cmdhistory", 5)
        await ws.send(json.dumps({
            "type":        "vocab",
            "commodities": commodities,
            "locations":   locations,
            "ships":       ships,
            "voyages":     voyages,
            "cmdhistory":  cmdhistory,
            "terminals":   sorted({
                f"{_loc(t.name)} ({t.star_system_name})"
                for t in (cache.terminals or [])
                if t.star_system_name
            }),
        }))

    # ── Complétion ────────────────────────────────────────────────────────────

    async def _handle_complete(self, ws, text: str, cursor: int) -> None:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._complete_sync, text, cursor)
        await ws.send(json.dumps({"type": "completions",
                                   "common_prefix": result.get("common_prefix", ""),
                                   "items": result.get("items", [])}))

    def _complete_sync(self, text: str, cursor: int) -> dict:
        """Complétion contextuelle riche.

        Retourne {"common_prefix": str, "items": [{"value", "hint", "insert"}, ...]}.
        - value  : texte affiché dans la liste (lisible)
        - hint   : description courte (type, fabricant, etc.)
        - insert : texte à insérer à la place du mot courant
        """
        try:
            return self._complete_impl(text, cursor)
        except Exception as e:
            print(f"[overlay] complete error: {e}", flush=True)
            return {"common_prefix": "", "items": []}

    # ── Helpers complétion ────────────────────────────────────────────────────

    @staticmethod
    def _common_prefix(strings: list[str]) -> str:
        """Calcule le préfixe commun d'une liste de chaînes (insensible à la casse)."""
        if not strings:
            return ""
        ref = strings[0].lower()
        length = len(ref)
        for s in strings[1:]:
            s_lo = s.lower()
            length = min(length, len(s_lo))
            for i in range(length):
                if ref[i] != s_lo[i]:
                    length = i
                    break
        return strings[0][:length]

    @staticmethod
    def _mk(value: str, hint: str = "", insert: str = "") -> dict:
        return {"value": value, "hint": hint, "insert": insert or value}

    def _complete_impl(self, text: str, cursor: int) -> dict:
        from uexinfo.cli.completer_data import SUBS, NEXT_TYPE, CMD_HINTS
        from uexinfo.cli.commands import get_names

        cur    = cursor if cursor >= 0 else len(text)
        before = text[:cur]

        # ── Extraire le mot courant et le préfixe de ligne ────────────────
        if before.endswith(" "):
            current_word = ""
            line_prefix  = before
        else:
            parts        = before.rsplit(" ", 1)
            current_word = parts[-1] if parts else ""
            line_prefix  = (parts[0] + " ") if len(parts) > 1 else ""

        q = current_word.lower().lstrip("/")

        # ── Déterminer la commande racine et la profondeur ─────────────────
        tokens = before.strip().split()
        cmd    = tokens[0].lstrip("/").lower() if tokens else ""
        depth  = len(tokens) - (0 if before.endswith(" ") else 1)
        # sous-commande déjà tapée (depth≥1)
        sub1   = tokens[1].lower() if len(tokens) > 1 else ""

        # ── Candidats selon le contexte ───────────────────────────────────
        candidates: list[dict] = []

        # — Cas @ : complétion des lieux (@local, @dest, @NomTerminal) ————————
        if current_word.startswith("@"):
            from uexinfo.cache.data_manager import _loc_short as _ls
            loc_q = current_word[1:].lower().replace("_", " ")
            at_items: list[dict] = []
            for shortcut, hint in [("@local", "position courante"),
                                   ("@dest",  "destination joueur")]:
                if not loc_q or shortcut[1:].startswith(loc_q):
                    at_items.append(self._mk(shortcut, hint, shortcut))
            if self.ctx and self.ctx.cache:
                seen_shorts: set[str] = set()
                for t in (self.ctx.cache.terminals or []):
                    name = t.name or ""
                    if not name:
                        continue
                    short = _ls(name)          # "Admin - CRU-L5" → "CRU-L5"
                    if short in seen_shorts:
                        continue
                    seen_shorts.add(short)
                    sl = short.lower()
                    if loc_q and not (sl.startswith(loc_q) or loc_q in sl):
                        continue
                    system = getattr(t, "star_system_name", "") or ""
                    at_items.append(self._mk(
                        f"@{short}", f"terminal · {system}",
                        f"@{short.replace(' ', '_')}",
                    ))
            at_items = at_items[:40]
            cp = self._common_prefix([c["insert"] for c in at_items]) if at_items else ""
            return {"common_prefix": cp, "items": at_items}

        # — Cas 0 : notation pointée dans le mot courant (RSI.hermes, ship.anvil) ——
        if current_word and "." in current_word and not current_word.startswith("/"):
            dot_items = self._complete_dotted(current_word)
            if dot_items is not None:
                cp = self._common_prefix([c["insert"] for c in dot_items]) if dot_items else ""
                return {"common_prefix": cp, "items": dot_items}

        # — Cas 1 : ligne vide ou saisie d'une commande (commence par /) ——
        if not tokens or (len(tokens) == 1 and not before.endswith(" ")):
            # Commandes enregistrées
            for name in sorted(get_names()):
                hint = CMD_HINTS.get(name, "")
                candidates.append(self._mk(f"/{name}", hint, f"/{name}"))
            # Lieux, commodités, vaisseaux (saisie libre sans /)
            if current_word and not current_word.startswith("/"):
                candidates += self._dyn_any(current_word)

        # — Cas 2 : après une commande connue ——————————————————————————————
        elif depth == 1 and before.endswith(" "):
            # Sous-commandes statiques
            ctx_key = cmd
            for sub, hint in SUBS.get(ctx_key, []):
                candidates.append(self._mk(sub, hint, sub))
            # Éléments dynamiques selon NEXT_TYPE
            ntype = NEXT_TYPE.get(ctx_key)
            if ntype:
                candidates += self._dyn_typed(ntype, "")

        # — Cas 3 : tapé le début de la sous-commande ——————————————————————
        elif depth == 1 and not before.endswith(" "):
            ctx_key = cmd
            for sub, hint in SUBS.get(ctx_key, []):
                candidates.append(self._mk(sub, hint, sub))
            ntype = NEXT_TYPE.get(ctx_key)
            if ntype:
                candidates += self._dyn_typed(ntype, "")

        # — Cas 4 : profondeur 2+ ——————————————————————————————————————————
        else:
            # Chercher sous-commandes de niveau 2 (ex: "voyage calc")
            ctx_key2 = f"{cmd} {sub1}"
            subs2    = SUBS.get(ctx_key2, [])
            if before.endswith(" "):
                for sub, hint in subs2:
                    candidates.append(self._mk(sub, hint, sub))
                ntype2 = NEXT_TYPE.get(ctx_key2) or NEXT_TYPE.get(cmd)
                if ntype2:
                    candidates += self._dyn_typed(ntype2, "")
            else:
                for sub, hint in subs2:
                    candidates.append(self._mk(sub, hint, sub))
                ntype2 = NEXT_TYPE.get(ctx_key2) or NEXT_TYPE.get(cmd)
                if ntype2:
                    candidates += self._dyn_typed(ntype2, "")

        # ── Filtrage et tri : préfixe d'abord, sous-chaîne ensuite ────────
        if q:
            prefix_m  = [c for c in candidates
                         if c["insert"].lower().startswith(q)]
            contain_m = [c for c in candidates
                         if q in c["insert"].lower()
                         and not c["insert"].lower().startswith(q)]
            filtered = prefix_m + contain_m
        else:
            filtered = candidates

        # Dédupliquer sur insert
        seen: set[str] = set()
        deduped: list[dict] = []
        for c in filtered:
            key = c["insert"].lower()
            if key not in seen:
                seen.add(key)
                deduped.append(c)

        items = deduped[:40]

        # ── Préfixe commun des inserts ────────────────────────────────────
        cp = self._common_prefix([c["insert"] for c in items]) if items else ""

        return {"common_prefix": cp, "items": items}

    def _dyn_any(self, q: str) -> list[dict]:
        """Retourne terminaux + commodités + vaisseaux du joueur pour la saisie libre."""
        results: list[dict] = []
        results += self._dyn_typed("any", q)
        return results

    def _complete_dotted(self, word: str) -> list[dict] | None:
        """Complétion contextuelle pour la notation pointée.

        Préfixes reconnus :
          ship.<mfr|nom>      → vaisseaux filtrés par fabricant / nom
          <ABBREV>.<nom>      → vaisseaux du fabricant (RSI.hermes, DRAK.cutlass…)
          commodity.<nom>     → commodités

        Retourne None si le préfixe n'est pas reconnu (délègue au moteur normal).
        """
        from uexinfo.cli.completer_data import MFR_ABBREV

        parts   = word.split(".", 1)
        pfx_raw = parts[0]                             # casse d'origine pour l'insert
        pfx     = pfx_raw.lower().replace("_", " ").strip()
        sfx     = parts[1].lower().replace("_", " ").strip() if len(parts) > 1 else ""

        # ── Vaisseaux ──────────────────────────────────────────────────────────
        is_ship   = pfx in ("ship", "vaisseau", "s")
        mfr_pfix  = MFR_ABBREV.get(pfx)   # ex: "rsi" → "robert"

        if is_ship or mfr_pfix is not None:
            if not self.ctx or not self.ctx.cache:
                return []
            results: list[dict] = []
            for v in (self.ctx.cache.vehicles or []):
                vname = getattr(v, "name_full", "") or getattr(v, "name", "") or ""
                if not vname:
                    continue
                mfr = (getattr(v, "manufacturer", "") or "").lower()
                # Filtrer par fabricant si abréviation connue
                if mfr_pfix and not mfr.startswith(mfr_pfix):
                    continue
                # Filtrer par nom si suffixe présent
                if sfx:
                    vl = vname.lower()
                    if not (vl.startswith(sfx)
                            or sfx in vl
                            or any(w.startswith(sfx.split()[0]) for w in vl.split() if sfx.split())):
                        continue
                # Insert = nom seul (sans le préfixe dot) pour ne pas polluer /ship add etc.
                insert = vname.replace(" ", "_")
                hint   = f"vaisseau · {mfr.title()}" if mfr else "vaisseau"
                results.append(self._mk(vname, hint, insert))
            return sorted(results, key=lambda c: c["value"].lower())[:40]

        # ── Commodités ─────────────────────────────────────────────────────────
        if pfx in ("commodity", "com", "commodité"):
            if not self.ctx or not self.ctx.cache:
                return []
            results = []
            for c in (self.ctx.cache.commodities or []):
                cname = c.name or ""
                kind  = getattr(c, "kind", "") or "commodité"
                if sfx and not (cname.lower().startswith(sfx) or sfx in cname.lower()):
                    continue
                insert = f"{pfx_raw}.{cname.replace(' ', '_')}"
                results.append(self._mk(cname, kind, insert))
            return results[:40]

        return None  # préfixe non reconnu → déléguer au moteur normal

    def _dyn_typed(self, ntype: str, q: str) -> list[dict]:
        """Retourne des suggestions dynamiques selon le type attendu."""
        if not self.ctx:
            return []
        results: list[dict] = []

        do_loc    = ntype in ("location", "terminal", "any")
        do_com    = ntype in ("commodity", "any")
        do_veh    = ntype in ("vehicle", "any")
        do_ship   = ntype == "any"  # vaisseaux joueur en priorité dans "any"
        do_sys    = ntype == "system"
        do_sel_loc = ntype == "sel_loc"

        # — Systèmes stellaires (pour /explore) ————————————————————————————
        if do_sys and self.ctx.cache:
            for s in (self.ctx.cache.star_systems or []):
                name = getattr(s, "name", "") or ""
                if not name:
                    continue
                insert = name.lower().replace(" ", "_")
                results.append(self._mk(name, "système stellaire", insert))

        # — Vaisseaux du joueur (priorité dans "any") ——————————————————————
        player_ship_names: set[str] = set()
        if do_ship:
            player = getattr(self.ctx, "player", None)
            if player:
                for s in (getattr(player, "ships", None) or []):
                    name = getattr(s, "name", "") or ""
                    if not name:
                        continue
                    player_ship_names.add(name.lower())
                    insert = name.replace(" ", "_")
                    results.append(self._mk(name, "vaisseau joueur", insert))

        # — Terminaux / lieux ——————————————————————————————————————————————
        if do_loc and self.ctx.cache:
            from uexinfo.cache.data_manager import _loc_short as _ls
            q_lower = q.lower().replace("_", " ") if q else ""
            seen_locs: set[str] = set()
            for t in (self.ctx.cache.terminals or []):
                name = t.name or ""
                if not name:
                    continue
                short = _ls(name)              # "Admin - CRU-L5" → "CRU-L5"
                if short in seen_locs:
                    continue
                seen_locs.add(short)
                sl = short.lower()
                insert = short.replace(" ", "_")
                if q_lower and not (sl.startswith(q_lower) or q_lower in sl):
                    continue
                system = getattr(t, "star_system_name", "") or ""
                results.append(self._mk(short, f"terminal · {system}", insert))
                if len(seen_locs) >= (40 if q_lower else 80):
                    break

        # — Commodités ——————————————————————————————————————————————————————
        if do_com and self.ctx.cache:
            q_lower = q.lower() if q else ""
            for c in (self.ctx.cache.commodities or []):
                name   = c.name or ""
                insert = name.replace(" ", "_")
                if q_lower and not (insert.lower().startswith(q_lower)
                                    or q_lower in insert.lower()):
                    continue
                kind = getattr(c, "kind", "") or "commodité"
                results.append(self._mk(name or insert, kind, insert))

        # — Noms de lieux (station/outpost/city) pour /select station|outpost|city ——
        if do_sel_loc and self.ctx.cache:
            q_lower = q.lower() if q else ""
            seen_sel: set[str] = set()
            for t in (self.ctx.cache.terminals or []):
                for field in ("space_station_name", "outpost_name", "city_name"):
                    lname = getattr(t, field, "") or ""
                    if not lname or lname in seen_sel:
                        continue
                    if q_lower and not (lname.lower().startswith(q_lower)
                                        or q_lower in lname.lower()):
                        continue
                    seen_sel.add(lname)
                    insert = lname.replace(" ", "_")
                    sys_name = getattr(t, "star_system_name", "") or ""
                    results.append(self._mk(lname, f"lieu · {sys_name}", insert))
                    if len(seen_sel) >= 60:
                        break
            if len(seen_sel) >= 60:
                pass  # limite atteinte, pas d'autre traitement nécessaire

        # — Catalogue complet vaisseaux (vehicle ou any) ———————————————————
        if do_veh and self.ctx.cache:
            q_lower   = q.lower() if q else ""
            veh_count = 0
            veh_limit = 50 if do_ship else 300
            for v in (self.ctx.cache.vehicles or []):
                name = getattr(v, "name_full", "") or getattr(v, "name", "") or ""
                if not name:
                    continue
                if name.lower() in player_ship_names:
                    continue
                insert = name.replace(" ", "_")
                if q_lower and not (insert.lower().startswith(q_lower)
                                    or q_lower in insert.lower()):
                    continue
                mfr = getattr(v, "manufacturer", "") or ""
                results.append(self._mk(name, f"vaisseau · {mfr}", insert))
                veh_count += 1
                if veh_count >= veh_limit:
                    break

        return results

    # ── Screenshot DB / OCR ───────────────────────────────────────────────────

    def _check_and_queue_screenshots(self) -> int:
        """Détecte les nouveaux screenshots et les soumet à l'OcrWorker.

        Retourne le nombre de nouveaux fichiers mis en queue.
        """
        if not self._ocr_worker or not self.ctx:
            return 0
        auto_ocr = self.ctx.cfg.get("scan", {}).get("auto_ocr", True)
        if not auto_ocr:
            return 0

        try:
            from uexinfo.cli.commands.scan import _screenshots_dir, _IMAGE_SUFFIXES
            sc_dir = _screenshots_dir(self.ctx)
            if not sc_dir.is_dir():
                return 0
            paths = [
                p for p in sc_dir.iterdir()
                if p.suffix.lower() in _IMAGE_SUFFIXES
            ]
            return self._ocr_worker.submit_many(paths)
        except Exception:
            return 0

    def _on_screenshot_processed(self, entry) -> None:
        """Callback OCR (depuis le thread worker) → broadcast WebSocket thread-safe."""
        if not self._loop or not self._clients:
            return
        # Compter les missions disponibles dans la fenêtre configurée
        try:
            import time as _t
            hours  = (self.ctx.cfg.get("scan", {}).get("hour", 2) if self.ctx else 2)
            since  = _t.time() - hours * 3600
            n_miss = len(self._screenshot_db.missions(since=since))
            n_term = len(self._screenshot_db.terminals(since=since))
        except Exception:
            n_miss, n_term = 0, 0

        pending = self._ocr_worker.qsize() if self._ocr_worker else 0
        msg = json.dumps({
            "type":     "screenshot_processed",
            "file":     entry.file,
            "sctype":   entry.type,
            "category": entry.category,
            "n_missions":  n_miss,
            "n_terminals": n_term,
            "errors":   entry.errors,
            "pending":  pending,
        })
        asyncio.run_coroutine_threadsafe(
            self._broadcast_raw(msg), self._loop
        )

    async def _broadcast_raw(self, msg: str) -> None:
        """Envoie un message brut JSON à tous les clients connectés."""
        for ws in list(self._clients):
            try:
                await ws.send(msg)
            except Exception:
                pass

    # ── Démarrage ─────────────────────────────────────────────────────────────

    async def _periodic_status(self) -> None:
        """Pousse le statut toutes les 10s — détecte les nouveaux screenshots sans interaction."""
        while True:
            await asyncio.sleep(10)
            if not self._clients or not self.ctx:
                continue
            # Soumettre les nouveaux screenshots à l'OCR worker
            n_queued = self._check_and_queue_screenshots()
            if n_queued > 0:
                await self._broadcast_raw(json.dumps({"type": "ocr_queued", "n": n_queued}))

            # Mode quick : vérifier le log SC-Datarunner et mettre à jour la position
            if self.ctx.cfg.get("scan", {}).get("log", {}).get("autopos", "off") == "quick":
                try:
                    from uexinfo.cli.commands.scan import check_log_auto
                    check_log_auto(self.ctx)  # déclenche _apply_autopos si terminal détecté
                    pending = getattr(self.ctx, "_overlay_msgs", [])
                    if pending:
                        for msg in pending:
                            await self._broadcast_raw(json.dumps(msg))
                        self.ctx._overlay_msgs = []
                except Exception:
                    pass

            for ws in list(self._clients):
                try:
                    await self._send_status(ws)
                except Exception:
                    pass

    async def serve(self, host: str = "localhost", port: int = 8090) -> None:
        async with websockets.serve(self.handler, host, port):
            asyncio.create_task(self._periodic_status())
            await asyncio.Future()  # tourne indéfiniment

    def start_background(self, host: str = "localhost", port: int = 8090) -> None:
        """Lance le serveur WebSocket dans un thread daemon."""
        ready = threading.Event()

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            ready.set()
            loop.run_until_complete(self.serve(host, port))

        t = threading.Thread(target=_run, daemon=True, name="overlay-ws")
        t.start()
        ready.wait(timeout=5)

    # ── Sélecteur interactif (appelé depuis le thread executor) ──────────────

    def _overlay_select_sync(
        self,
        ws,
        items: list,        # list[SelectItem]
        title: str,
        mode: str,
        confirm_label: str = "",
    ) -> list | None:
        """Envoie la liste au JS et attend la réponse (bloquant dans le thread exec)."""
        if self._loop is None:
            return None

        # Construire le message
        select_msg = json.dumps({
            "type":  "select",
            "mode":  mode,
            "title": title,
            "confirm_label": confirm_label,
            "items": [
                {"idx": i, "label": it.label, "meta": it.meta,
                 "selected": bool(getattr(it, "selected", False))}
                for i, it in enumerate(items)
            ],
        })

        # Envoyer depuis le thread asyncio
        self._select_event.clear()
        self._select_indices = None
        future = asyncio.run_coroutine_threadsafe(
            ws.send(select_msg), self._loop
        )
        try:
            future.result(timeout=5)
        except Exception:
            return None

        # Attendre la réponse JS (2 min max)
        if not self._select_event.wait(timeout=120):
            return None   # timeout

        indices = self._select_indices  # None si annulé
        if indices is None:
            return None
        return [items[i] for i in indices if 0 <= i < len(items)]
