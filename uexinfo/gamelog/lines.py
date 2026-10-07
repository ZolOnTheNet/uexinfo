"""Découpage d'une ligne brute de Game.log — pur, sans I/O (spec : docs/ai/GAMELOG_SPEC.md)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

_RE_HEAD = re.compile(
    r"^<(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)Z>\s*"
    r"(?:\[(?P<level>[A-Za-z]+)\]\s*)?"
    r"(?:<(?P<cat>[^>]{1,120})>\s*)?"
    r"(?P<msg>.*)$"
)
# Lignes très fréquentes et sans intérêt (spam).
SPAM_MARKERS = ("OnEntityEnterZone", "OnEntityLeaveZone")


@dataclass(frozen=True)
class LogLine:
    ts: datetime | None
    level: str          # "Notice", "Trace"… ou ""
    category: str       # contenu de <…> après le niveau, ou ""
    message: str
    raw: str


def parse_line(raw: str) -> LogLine:
    raw = raw.rstrip("\r\n")
    m = _RE_HEAD.match(raw)
    if not m:
        return LogLine(None, "", "", raw, raw)
    try:
        ts = datetime.strptime(m.group("ts"), "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        ts = None
    return LogLine(ts, m.group("level") or "", (m.group("cat") or "").strip(),
                   (m.group("msg") or "").strip(), raw)


def is_spam(raw: str) -> bool:
    return any(s in raw for s in SPAM_MARKERS)
