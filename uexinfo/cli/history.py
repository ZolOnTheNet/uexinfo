"""Historique persistant des commandes — ~/.uexinfo/history.jsonl."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import appdirs

_HISTORY_PATH = Path(appdirs.user_data_dir("uexinfo")) / "history.jsonl"


def load() -> list[str]:
    """Charge l'historique depuis le disque. Retourne la liste des commandes (les plus récentes en dernier)."""
    if not _HISTORY_PATH.exists():
        return []
    try:
        entries = []
        with open(_HISTORY_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    cmd = obj.get("cmd", "")
                    if cmd:
                        entries.append(cmd)
                except (json.JSONDecodeError, AttributeError):
                    pass
        return entries
    except OSError:
        return []


def append(command: str, html_output: str = "") -> None:
    """Ajoute une commande à l'historique sur disque, avec son output HTML optionnel."""
    if not command.strip():
        return
    try:
        _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry: dict = {"ts": datetime.now().isoformat(timespec="seconds"), "cmd": command}
        if html_output:
            entry["html"] = html_output
        with open(_HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def last_n(n: int = 100) -> list[str]:
    """Retourne les N dernières commandes uniques, les plus récentes en premier (index 0 = plus récente)."""
    all_cmds = load()
    seen: set[str] = set()
    result = []
    for cmd in reversed(all_cmds):
        if cmd not in seen:
            seen.add(cmd)
            result.append(cmd)
    return result[:n]  # result[0] = plus récente, result[-1] = plus ancienne


def last_n_raw(n: int = 5) -> list[str]:
    """Retourne les N dernières commandes brutes (avec doublons), les plus récentes en premier."""
    all_cmds = load()
    return list(reversed(all_cmds[-n:]))


def last_n_raw_with_output(n: int = 5) -> list[dict]:
    """Retourne les N dernières entrées brutes avec leur output HTML stocké.

    Retourne une liste de dicts {"cmd": ..., "html": ...}, les plus récentes en premier.
    Les entrées sans HTML ont html="".
    """
    if not _HISTORY_PATH.exists():
        return []
    try:
        entries = []
        with open(_HISTORY_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    cmd = obj.get("cmd", "")
                    if cmd:
                        entries.append({"cmd": cmd, "html": obj.get("html", "")})
                except (json.JSONDecodeError, AttributeError):
                    pass
        return list(reversed(entries[-n:]))
    except OSError:
        return []


def stats() -> dict:
    """Statistiques de l'historique."""
    all_cmds = load()
    if not _HISTORY_PATH.exists():
        return {"total": 0, "unique": 0, "size_kb": 0}
    return {
        "total": len(all_cmds),
        "unique": len(set(all_cmds)),
        "size_kb": _HISTORY_PATH.stat().st_size // 1024,
        "path": str(_HISTORY_PATH),
    }
