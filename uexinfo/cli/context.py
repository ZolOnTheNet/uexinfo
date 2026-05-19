"""AppContext — état global partagé entre les commandes et l'overlay."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from uexinfo.cache.manager import CacheManager
from uexinfo.cache.mission_manager import MissionManager
from uexinfo.cache.price_cache import PriceCache
from uexinfo.cache.voyage_manager import VoyageManager
from uexinfo.data.cargo_grids import CargoGridManager
from uexinfo.location.index import LocationIndex
from uexinfo.models.player import Player
from uexinfo.models.scan_result import ScanResult


@dataclass
class AppContext:
    cfg: dict = field(default_factory=dict)
    cache: CacheManager = field(default_factory=CacheManager)
    cargo_grid_manager: CargoGridManager = field(default_factory=CargoGridManager)
    location_index: LocationIndex | None = None
    player: Player = field(default_factory=Player)
    last_scan: ScanResult | None = None
    scan_history: list[ScanResult] = field(default_factory=list)
    _price_cache: PriceCache = field(default_factory=PriceCache)
    mission_manager: MissionManager = field(default_factory=MissionManager)
    voyage_manager: VoyageManager = field(default_factory=VoyageManager)
    screenshot_db: object | None = None   # ScreenshotDB (injecté par overlay)
    _api_offline: bool = False   # True quand UEX Corp API inaccessible → cache local
    _version_notice: tuple | None = None  # (stored, detected, env) → bannière à afficher
    debug_level: int = 0
    log_last_mtime: float = 0.0           # mtime du log lors du dernier check auto
    screenshots_last_seen_ts: float = 0.0  # wall-clock du dernier check screenshots
    select_fn: object = None              # callable | None — injecté par overlay server
    _cancel_flag: threading.Event = field(default_factory=threading.Event)
    _overlay_send_fn: object = None       # callable | None — injecté par overlay server
