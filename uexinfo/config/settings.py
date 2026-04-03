"""Configuration utilisateur — lecture/écriture ~/.uexinfo/config.toml"""
from __future__ import annotations

import tomllib
import tomli_w
from copy import deepcopy
from pathlib import Path

import appdirs

APP_NAME = "uexinfo"

CONFIG_PATH = Path(appdirs.user_config_dir(APP_NAME)) / "config.toml"

DEFAULT: dict = {
    "profile": {"username": ""},
    "ships": {"available": [], "current": ""},
    "cargo": {},
    "position": {"current": "", "destination": ""},
    "filters": {
        "systems": [],
        "planets": [],
        "stations": [],
        "terminals": [],
        "cities": [],
        "outposts": [],
    },
    "trade": {
        "min_profit_per_scu": 0,
        "min_margin_percent": 0,
        "max_distance": 0,
        "illegal_commodities": False,
    },
    "cache": {"ttl_static": 86400, "ttl_prices": 300},
    "player": {
        "username": "",
        "ships": [],
        "active_ship": "",
        "location": "",
        "destination": "",
    },
    "scan": {
        "mode":             "ocr",
        "tesseract_exe":    "",
        "sc_log_path":      "",
        "sc_screenshots_dir": "",
        "auto_ocr":         True,   # Lancer l'OCR dès qu'un nouveau screenshot est détecté
        "hour":             2,      # Fenêtre de recherche (heures en arrière) pour /mission scan
        "session_gap":      60,     # Gap en minutes entre deux screenshots = nouvelle session
    },
    "auto": {
        "log":          True,   # Lire le log SC-Datarunner automatiquement si chemin défini
        "signal_scan":  True,   # Signaler les nouveaux scans/screenshots détectés
        "log_accept":   True,   # Accepter automatiquement les valeurs lues depuis le log
    },
    "overlay": {
        "hotkey": "alt+shift+u",
        "port": 8090,
        "width": 700,
        "height": 900,
        "opacity": 0.95,
        "close": "normal",  # "normal" = ✕ ferme | "dblclick" = ✕ masque, double-clic ferme
        "clock": True,      # Afficher l'horloge en fond de fenêtre
    },
    "dev": {
        "enabled":     False,   # Mode développeur — bypass des comportements de production
        "skip_processed": True, # Si True : ignorer les fichiers déjà dans la DB lors d'un import
    },
    "voyage": {
        "calc": {
            "nbsaut":  5,    # Nb max de missions dans une proposition (--max)
            "prop":    1,    # Nb de propositions : 1=critère seul, ≥2=dist+benef+roi
            "options": "",   # Options par défaut (ex: "--boucle --station")
            "favoris": [],   # Lieux à privilégier (liste de noms)
            "exclure": [],   # Lieux à exclure systématiquement
            "gap_max": 3.0,  # Transit max entre missions avant ⚠ (Gm)
        }
    },
}


def load() -> dict:
    if not CONFIG_PATH.exists():
        return deepcopy(DEFAULT)
    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)
    merged = deepcopy(DEFAULT)
    _deep_merge(merged, data)
    return merged


def save(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "wb") as f:
        tomli_w.dump(cfg, f)


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
