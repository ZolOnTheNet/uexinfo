"""Convertisseur ANSI escape → HTML spans.

Port fidèle du convertisseur JS ANSI.toHtml() de l'overlay.
Utilisé pour stocker la sortie des commandes en HTML dans history.jsonl.
"""
from __future__ import annotations
import re

_BFG: dict[int, str] = {
    30: '#555',  31: '#e06c75', 32: '#98c379', 33: '#e5c07b',
    34: '#61afef', 35: '#c678dd', 36: '#56b6c2', 37: '#abb2bf',
    90: '#5c6370', 91: '#ff7b89', 92: '#b8f0b8', 93: '#fffb8f',
    94: '#88c0f0', 95: '#d9a3f0', 96: '#0ff',   97: '#fff',
}

_C256_BASE = [
    '#000', '#800', '#080', '#880', '#008', '#808', '#088', '#aaa',
    '#555', '#f55', '#5f5', '#ff5', '#55f', '#f5f', '#5ff', '#fff',
]

_RE_ANSI = re.compile(r'\x1b\[([0-9;]*)([mKJH])')


def _c256(n: int) -> str:
    if n < 16:
        return _C256_BASE[n] if n < len(_C256_BASE) else '#888'
    if n >= 232:
        v = 8 + (n - 232) * 10
        return f'rgb({v},{v},{v})'
    n -= 16
    b = n % 6; g = (n // 6) % 6; r = n // 36
    ci = lambda x: 55 + x * 40 if x else 0
    return f'rgb({ci(r)},{ci(g)},{ci(b)})'


def _esc(t: str) -> str:
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def ansi_to_html(raw: str) -> str:
    """Convertit une chaîne ANSI en HTML avec spans de style inline.

    Les newlines \\n sont préservés — le JS les utilisera pour créer les divs de ligne.
    """
    st: dict = {'b': False, 'd': False, 'i': False, 'u': False, 'fg': None, 'bg': None}

    def style() -> str:
        s = []
        if st['fg']: s.append(f"color:{st['fg']}")
        if st['bg']: s.append(f"background:{st['bg']}")
        if st['b'] and not st['d']: s.append('font-weight:bold')
        if st['d']: s.append('opacity:0.50')
        if st['i']: s.append('font-style:italic')
        if st['u']: s.append('text-decoration:underline')
        return ';'.join(s)

    segs: list[tuple[str, str]] = []
    last = 0

    for m in _RE_ANSI.finditer(raw):
        if m.start() > last:
            segs.append((style(), raw[last:m.start()]))
        last = m.end()
        if m.group(2) != 'm':
            continue
        codes = [int(x) for x in m.group(1).split(';')] if m.group(1) else [0]
        ci = 0
        while ci < len(codes):
            c = codes[ci]; ci += 1
            if c == 0:
                st = {'b': False, 'd': False, 'i': False, 'u': False, 'fg': None, 'bg': None}
            elif c == 1:  st['b'] = True
            elif c == 2:  st['d'] = True
            elif c == 3:  st['i'] = True
            elif c == 4:  st['u'] = True
            elif c == 22: st['b'] = False; st['d'] = False
            elif c == 23: st['i'] = False
            elif c == 24: st['u'] = False
            elif 30 <= c <= 37: st['fg'] = _BFG.get(c)
            elif c == 38:
                sub = codes[ci]; ci += 1
                if sub == 5:
                    st['fg'] = _c256(codes[ci]); ci += 1
                elif sub == 2:
                    r2, g2, b2 = codes[ci], codes[ci+1], codes[ci+2]; ci += 3
                    st['fg'] = f'rgb({r2},{g2},{b2})'
            elif c == 39: st['fg'] = None
            elif 40 <= c <= 47: st['bg'] = _BFG.get(c - 10)
            elif c == 48:
                sub = codes[ci]; ci += 1
                if sub == 5:
                    st['bg'] = _c256(codes[ci]); ci += 1
                elif sub == 2:
                    r2, g2, b2 = codes[ci], codes[ci+1], codes[ci+2]; ci += 3
                    st['bg'] = f'rgb({r2},{g2},{b2})'
            elif c == 49: st['bg'] = None
            elif 90 <= c <= 97: st['fg'] = _BFG.get(c)

    if last < len(raw):
        segs.append((style(), raw[last:]))

    parts: list[str] = []
    for s, t in segs:
        if not t:
            continue
        e = _esc(t)
        parts.append(f'<span style="{s}">{e}</span>' if s else e)

    return ''.join(parts)
