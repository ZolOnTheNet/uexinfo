"""Catalogue des contrats du jeu → reconnaissance des cartes lues dans le mobiGlas.

Sources, par ordre de préférence :
1. **scmdb.net** (données extraites du jeu : récompense, points d'événement, catégories, partage
   des points en groupe). Licence CC BY-NC-ND 4.0 : rien n'est versionné ni redistribué ; le fichier
   est gardé dans le cache utilisateur (`appdirs.user_cache_dir('uexinfo')/scmdb/`) et n'est
   téléchargé que sur demande explicite (`download_scmdb`, via `/mission offres maj`).
2. **global.ini** du jeu installé : titres seuls (plus l'XP si la traduction PolyToolSC est active).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import appdirs

SCMDB_BASE = "https://scmdb.net/data/"
SCMDB_CREDIT = "Données : SCMDB (scmdb.net), CC BY-NC-ND 4.0"
_USER_AGENT = "uexinfo (outil Star Citizen non commercial ; https://github.com/ZolOnTheNet/uexinfo)"

MATCH_MIN = 80            # score minimal (0-100) pour considérer un contrat reconnu
_MERGE_GAIN = 5           # gain de score requis pour recoller une carte coupée à la suivante

# Catégories d'événement (eventScopes.category) → libellé affiché
CATEGORY_FR = {"Transport": "Transport", "Defense": "Défense", "Collection": "Collection", None: "Total"}


@dataclass
class CatalogContract:
    """Un contrat du jeu tel que décrit par le catalogue : titre, récompense, points de réputation par catégorie."""
    title: str
    debug_name: str = ""
    reward: int | None = None                       # aUEC
    points: dict[str, int] = field(default_factory=dict)   # « Transport » → 625 ; « Total » → 625
    event: str = ""                                  # nom de code de l'événement (ex. « Iasi »)
    split_party: bool = False                        # points divisés entre les membres du groupe
    source: str = "scmdb"

    @property
    def xp(self) -> int | None:
        """Points de réputation gagnés : le total s'il est connu, sinon la plus forte catégorie."""
        return self.points.get("Total") or (max(self.points.values()) if self.points else None)

    @property
    def category(self) -> str:
        """Catégorie de réputation (Transport, Défense…), ou « » si seul le total est connu."""
        return next((c for c in self.points if c != "Total"), "")


@dataclass
class RecognizedContract:
    """Une carte lue à l'écran rapprochée de son contrat dans le catalogue, avec le score de ressemblance."""
    card: object                                    # ContractCard (ou équivalent : title, xp, reward…)
    contract: CatalogContract | None
    score: float
    reward_from_catalog: bool = False               # montant non lu ou incohérent → récompense du catalogue

    @property
    def recognized(self) -> bool:
        """Vrai si un contrat a été trouvé avec un score suffisant (MATCH_MIN)."""
        return self.contract is not None and self.score >= MATCH_MIN

    @property
    def reward(self) -> int | None:
        """Récompense à afficher : celle du catalogue si le montant lu est absent ou incohérent, sinon celle lue."""
        if self.reward_from_catalog and self.contract:
            return self.contract.reward
        return getattr(self.card, "reward", None)

    @property
    def xp(self) -> int | None:
        """Points à afficher : ceux du catalogue si le contrat est reconnu, sinon ceux lus sur la carte."""
        if self.recognized and self.contract.xp:
            return self.contract.xp
        return getattr(self.card, "xp", None)


def normalize(title: str) -> str:
    """Titre comparable : sans balises ni « NNN exp. », majuscules, ponctuation réduite."""
    t = re.sub(r"</?EM\d>", " ", title or "")
    t = re.sub(r"\d{2,5}\s*EXP\b\.?", " ", t, flags=re.I)
    t = t.upper().replace("RS/", "RSI").replace("|", "I")
    t = re.sub(r"[^A-Z0-9()\[\] ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _without_placeholders(title: str) -> str:
    """« Critical Refuel Request ([SHIP]) » → « Critical Refuel Request » (variable remplacée en jeu)."""
    return re.sub(r"\s*\(?\[[^\]]+\]\)?", "", title).strip()


class ContractCatalog:
    """Catalogue des contrats, indexé par titre normalisé pour reconnaître les cartes lues par OCR."""
    def __init__(self, contracts: list[CatalogContract], source: str, version: str = ""):
        """Indexe les contrats par titre complet et par titre sans préfixe ; `source` : « scmdb » ou « global.ini »."""
        self.contracts = contracts
        self.source = source
        self.version = version
        self._by_key: dict[str, list[CatalogContract]] = {}
        # Titre sans son préfixe (« RSI Disc. Month: … ») : le jeu peut l'afficher autrement
        # (« <REDACTED>: … » avant le début d'un événement) ou l'OCR le perdre.
        self._by_suffix: dict[str, list[CatalogContract]] = {}
        for c in contracts:
            for title in {c.title, _without_placeholders(c.title)}:
                self._by_key.setdefault(normalize(title), []).append(c)
                if ":" in title:
                    self._by_suffix.setdefault(normalize(title.split(":", 1)[1]), []).append(c)
        self._keys = list(self._by_key)
        self._suffix_keys = list(self._by_suffix)

    def __len__(self) -> int:
        """Nombre de contrats du catalogue."""
        return len(self.contracts)

    # ── Construction ─────────────────────────────────────────────────────────

    @classmethod
    def from_scmdb(cls, data: dict) -> "ContractCatalog":
        """Catalogue depuis la copie locale de scmdb.net (points par catégorie, partage en groupe, récompense)."""
        scopes = data.get("eventScopes") or {}
        out = []
        for c in data.get("contracts") or []:
            title = (c.get("title") or "").strip()
            if not title or title.startswith("@"):
                continue
            points, event, split = {}, "", False
            for t in c.get("completionTags") or []:
                scope = scopes.get(t.get("tag"))
                if not scope:
                    continue
                points[CATEGORY_FR.get(scope.get("category"), scope.get("category"))] = int(t.get("count") or 0)
                event = scope.get("eventName") or event
                split = split or bool(t.get("splitPointsForParty"))
            out.append(CatalogContract(title=title, debug_name=c.get("debugName") or "",
                                       reward=c.get("rewardUEC"), points=points, event=event,
                                       split_party=split, source="scmdb"))
        return cls(out, "scmdb", str(data.get("version") or ""))

    @classmethod
    def from_global_ini(cls, path: Path) -> "ContractCatalog":
        """Catalogue depuis le `global.ini` du jeu (textes traduits).

        Seuls les titres qui portent un nombre d'XP (« <EM4>625 exp.</EM4> ») sont des
        titres de contrat ; la récompense n'y figure pas.
        """
        out, seen = [], set()
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                key, sep, val = line.partition("=")
                if not sep or not re.search(r"_title(_\d+)?(,P)?$", key.strip(), re.I):
                    continue
                m = re.search(r"<EM\d>\s*(\d+)\s*exp\.?\s*</EM\d>", val, re.I)
                title = re.sub(r"\s*<EM\d>.*?</EM\d>\s*", " ", val).strip()
                if not title or not m or title in seen:     # sans XP : pas un titre de contrat
                    continue
                seen.add(title)
                out.append(CatalogContract(title=title, debug_name=key.strip(),
                                           points={"Total": int(m.group(1))}, source="global.ini"))
        return cls(out, "global.ini")

    # ── Reconnaissance ───────────────────────────────────────────────────────

    def match(self, text: str, reward: int | None = None, xp: int | None = None):
        """Meilleur contrat pour un titre lu → (contrat | None, score 0-100)."""
        from rapidfuzz import fuzz, process
        if not normalize(text) or not self._keys:
            return None, 0.0
        # Essais : titre lu tel quel, puis sans sa dernière parenthèse (variable du jeu remplacée :
        # « (ORIGIN 400i) » pour « ([SHIP]) ») ; contre les titres complets, et contre les titres
        # sans préfixe si le titre lu n'en a pas.
        texts = {text, re.sub(r"\s*\([^()]*\)\s*$", "", text)}
        scored: list[tuple[float, CatalogContract]] = []
        for t in texts:
            key = normalize(t)
            if not key:
                continue
            tries = [(self._keys, self._by_key)]
            if ":" not in t and self._suffix_keys:
                tries.append((self._suffix_keys, self._by_suffix))
            for keys, tab in tries:
                for k, score, _ in process.extract(key, keys, scorer=fuzz.token_sort_ratio, limit=5):
                    scored += [(float(score), c) for c in tab[k]]
        if not scored:
            return None, 0.0
        top = max(sc for sc, _ in scored)
        cands = list({id(c): c for sc, c in scored if sc >= top - 0.01}.values())
        # Ex-aequo (variantes au même titre, version d'événement ou non) : la récompense puis
        # l'XP affichées départagent.
        if len(cands) > 1 and (reward or xp):
            cands.sort(key=lambda c: (abs((c.reward or 0) - (reward or c.reward or 0)),
                                      abs((c.xp or 0) - (xp or c.xp or 0))))
        return cands[0], top

    def recognize(self, cards: list) -> list[RecognizedContract]:
        """Cartes lues → contrats. Recolle une carte coupée en haut d'écran à la suivante et
        écarte les en-têtes de catégorie (cartes sans récompense ni minuteur, non reconnues)."""
        out: list[RecognizedContract] = []
        i = 0
        while i < len(cards):
            card = cards[i]
            fragment = not (card.reward is not None or getattr(card, "timer", ""))
            if fragment and i + 1 < len(cards):
                nxt = cards[i + 1]
                alone = self.match(nxt.title, nxt.reward, nxt.xp)
                merged = self.match(f"{card.title} {nxt.title}", nxt.reward, nxt.xp)
                if merged[1] >= alone[1] + _MERGE_GAIN:
                    from dataclasses import replace
                    out.append(self._result(replace(nxt, title=f"{card.title} {nxt.title}",
                                                    raw=f"{card.raw} {nxt.raw}"), *merged))
                    i += 2
                    continue
            res = self._result(card, *self.match(card.title, card.reward, card.xp))
            # En-tête de catégorie (« RSI DISCOVERY EVENT 27 ») : ni montant, ni XP, ni donneur d'ordre.
            header = fragment and not res.recognized and card.xp is None and not getattr(card, "contractor", "")
            if not header:
                out.append(res)
            i += 1
        return out

    @staticmethod
    def _result(card, contract, score) -> RecognizedContract:
        """Construit le résultat et décide si la récompense du catalogue doit remplacer celle lue."""
        r = RecognizedContract(card, contract, score)
        if r.recognized and contract.reward:
            read = getattr(card, "reward", None)
            # Montant non lu, ou trop éloigné (« 1k » pour 51 500) : celui du catalogue fait foi.
            r.reward_from_catalog = read is None or abs(read - contract.reward) > max(2000, 0.1 * contract.reward)
        return r


# ── Fichiers ──────────────────────────────────────────────────────────────────

def scmdb_cache_dir() -> Path:
    """Dossier des copies locales de scmdb.net (cache utilisateur, jamais dans le dépôt)."""
    return Path(appdirs.user_cache_dir("uexinfo")) / "scmdb"


def cached_scmdb_files() -> list[Path]:
    """Fichiers scmdb téléchargés, du plus ancien au plus récent."""
    d = scmdb_cache_dir()
    return sorted(d.glob("merged-*.json"), key=lambda p: p.stat().st_mtime) if d.is_dir() else []


def download_scmdb(timeout: float = 60) -> Path:
    """Télécharge la dernière version de scmdb si elle n'est pas déjà en cache. Appel explicite seulement."""
    import requests
    headers = {"User-Agent": _USER_AGENT}
    versions = requests.get(SCMDB_BASE + "versions.json", headers=headers, timeout=timeout).json()
    name = versions[0]["file"]
    if not re.fullmatch(r"merged-[\w.\-]+\.json", name):
        raise ValueError(f"nom de fichier inattendu : {name!r}")
    dest = scmdb_cache_dir() / name
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(SCMDB_BASE + name, headers=headers, timeout=timeout)
    r.raise_for_status()
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(r.content)
    tmp.replace(dest)
    return dest


def global_ini_path(cfg: dict) -> Path | None:
    """global.ini de la langue configurée dans user.cfg (g_language), à côté de Game.log."""
    install = (cfg.get("gamelog") or {}).get("install_path_live") or ""
    if not install:
        return None
    root = Path(install)
    lang = "english"
    try:
        m = re.search(r"^\s*g_language\s*=\s*(\S+)", (root / "user.cfg").read_text(encoding="utf-8", errors="replace"), re.M)
        lang = m.group(1) if m else lang
    except OSError:
        pass
    p = root / "data" / "Localization" / lang / "global.ini"
    return p if p.is_file() else None


def load_catalog(cfg: dict) -> ContractCatalog | None:
    """Catalogue le plus complet disponible localement (sans accès réseau)."""
    files = cached_scmdb_files()
    if files:
        try:
            with open(files[-1], encoding="utf-8") as f:
                return ContractCatalog.from_scmdb(json.load(f))
        except (OSError, ValueError):
            pass
    p = global_ini_path(cfg)
    if p:
        cat = ContractCatalog.from_global_ini(p)
        if len(cat):
            return cat
    return None
