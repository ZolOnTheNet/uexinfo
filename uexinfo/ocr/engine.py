"""Moteur OCR Tesseract — extraction des terminaux SC.

Pipeline (inspiré de SC-Datarunner-UEX) :
  1. Crop gauche  → terminal name  (PSM 7, terminals.user-words)
  2. Crop droite  → commodity list (PSM 4, commodities.user-words + sc.patterns)
  3. TSV image_to_data → lignes triées par position Y
  4. Machine à états : NOM → SCU → STOCK → PRIX  (4 éléments par commodité)
"""
from __future__ import annotations

import os
import re
import statistics
from pathlib import Path

from uexinfo.models.scan_result import ScannedCommodity, ScanResult
from uexinfo.models.mission_result import MissionResult, ParsedObjective

# ── Chemins ──────────────────────────────────────────────────────────────────

_BASE          = Path(__file__).parents[2] / "extprg" / "SC-Datarunner-UEX"
_DEFAULT_DATA  = _BASE / "data"
_WIN_EXE       = _BASE / "dep" / "Tesseract-OCR" / "tesseract.exe"
_LINUX_EXE     = Path("/usr/bin/tesseract")


def _find_exe() -> Path:
    """Windows bundled .exe > Linux /usr/bin/tesseract > PATH."""
    if _WIN_EXE.exists():
        return _WIN_EXE
    if _LINUX_EXE.exists():
        return _LINUX_EXE
    return Path("tesseract")


def _img_size(image_path: Path) -> tuple[int, int]:
    """Retourne (width, height) sans charger toute l'image."""
    from PIL import Image
    with Image.open(image_path) as im:
        return im.size


# ── Patterns mission ──────────────────────────────────────────────────────────

_RE_REWARD      = re.compile(r"Reward\s+[¤øH$]?\s*([\d,\s]+)", re.IGNORECASE)
_RE_CONTRACTED  = re.compile(r"Contracted\s+By\s+(.+)", re.IGNORECASE)
_RE_AVAIL       = re.compile(r"Contract\s+Availability\s+(.+)", re.IGNORECASE)
_RE_MISSION_AMT = re.compile(r"(\d+)\s*[kK]$")   # "40k" dans la liste de missions
_RE_BULLET      = re.compile(r"^[•◇◆\-\*\u25c6\u2666\u00b7]\s*")

# ── Patterns parsing structuré des objectifs ──────────────────────────────────
# OCR introduit des préfixes parasites : ©, <, >, |, [ etc.
_RE_OBJ_NOISE   = re.compile(r"^[©<>|\[\]]+\s*")
# "Collect <commodity> from <location>"
_RE_OBJ_COLLECT = re.compile(r"collect\s+(.+?)\s+from\s+(.+)", re.IGNORECASE)
# "Deliver 0/53 SCU of <commodity> to <location>"  (location peut être coupée)
_RE_OBJ_DELIVER = re.compile(
    r"deliver\s+\d+/(\d+)\s*SCU\s+of\s+(.+?)(?:\s+to\s+(.+))?$", re.IGNORECASE
)
# Continuation "above <planet>" (fin ou continuation de ligne)
_RE_OBJ_ABOVE   = re.compile(r"above\s+(.+?)\.?\s*$", re.IGNORECASE)
# Format alternatif ACCEPTED : "at ArcCorp's L2 Lagrange point" → hint = "ArcCorp L2"
_RE_OBJ_AT_LAGRANGE = re.compile(
    r"\s+at\s+(.+?)(?:'s\s+L\d\s+Lagrange\s+point)?\.?\s*$", re.IGNORECASE
)
# Boutons UI à ignorer
_RE_OBJ_UI      = re.compile(
    r"^(ACCEPT\s+OFFER|MARK\s+ALL|PRIMARY\s+OBJ|CONTRACT\s+AVAIL|CONTRACTED\s+BY)",
    re.IGNORECASE
)
# Format Dispo depuis l'UI : "1h 56m" ou "0h 23m" ou "23m"
_RE_DISPO       = re.compile(r"Dispo\s*[:\-]?\s*(\d+h\s*\d+m|\d+m)", re.IGNORECASE)

_MISSION_KEYWORDS = {
    "OFFERS", "ACCEPTED", "HISTORY",
    "PRIMARY OBJECTIVES", "CONTRACT AVAILABILITY",
    "CONTRACTED BY", "ACCEPT OFFER", "MARK ALL READ",
}
_TERMINAL_KEYWORDS = {
    "SHOP INVENTORY", "SELLABLE CARGO", "IN DEMAND",
    "COMMODITIES", "LOCAL MARKET VALUE",
}

# ── Patterns de parsing ───────────────────────────────────────────────────────

# ø = U+00F8 (symbole monétaire SC), ¤ = fallback ASCII, H = misread OCR fréquent de ¤/ø
# SC[UY] : OCR confond U↔Y en fin de "SCU/SCY"
_RE_SCU        = re.compile(r"^(\d[\d,]*)\s*SCU$", re.IGNORECASE)
_RE_SCU_INLINE = re.compile(r"(\d[\d,]*)\s+SCU", re.IGNORECASE)   # * pour "0 SCU"
_RE_PRICE_K    = re.compile(r"[ø¤H]\s*(\d[\d,.]+)\s*K\s*/\s*SC[UY]", re.IGNORECASE)
_RE_PRICE_M    = re.compile(r"[ø¤H]\s*(\d[\d,.]+)\s*M\s*/\s*SC[UY]", re.IGNORECASE)
_RE_PRICE      = re.compile(r"[ø¤H]\s*(\d[\d,.]+)\s*/\s*SC[UY]", re.IGNORECASE)

# Niveaux de stock : label → status_code (1=vide … 7=max)
_STOCK_LEVELS: list[tuple[str, int]] = [
    ("max inventory",        7),
    ("very high inventory",  6),
    ("high inventory",       5),
    ("medium inventory",     4),
    ("low inventory",        3),
    ("very low inventory",   2),
    ("out of stock",         1),
]

# Préfixes d'interface SC à ignorer (sans ancre $ — la ligne peut avoir une suite comme "(SCU)")
_SKIP_STARTS_RE = re.compile(
    r"^(AVAILABLE\s+CARGO\s+SIZE|SHOP\s+(INVENTORY|QUANTITY)|YOUR\s+INVENTORIES|"
    r"SELLABLE\s+CARGO|IN\s*DEMAND|IN\s+STOCK|NO\s+DEMAND|CANNOT\s+SELL|"
    r"LOCAL\s+MARKET\s+VALUE|CURRENT\s+BALANCE|COMMODITIES|BUY\b)",
    re.IGNORECASE,
)
# Détection des changements de section du panneau de vente
_SECTION_SELLABLE_RE = re.compile(r"^SELLABLE\s+CARGO", re.IGNORECASE)
_SECTION_INDEMAND_RE = re.compile(r"^IN\s*DEMAND", re.IGNORECASE)
# Suffixes d'interface SC collés aux noms de commodités ("WASTE SHOP QUANTITY")
_RE_UI_SUFFIX = re.compile(r"\s+SHOP\s+(QUANTITY|INVENTORY)\s*$", re.IGNORECASE)
# Lignes de bruit pur : chiffres, boutons cargo (1 2 4 8 16 32), symboles seuls
_SKIP_NOISE_RE = re.compile(r"^[\d\s()\[\]~\"\'\\¤ø.,:;/\-]+$")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_price(text: str) -> int | None:
    """Extrait le prix en aUEC depuis une chaîne OCR. Gère K/M suffixes."""
    m = _RE_PRICE_K.search(text)
    if m:
        try:
            return round(float(m.group(1).replace(",", ".")) * 1_000)
        except ValueError:
            pass
    m = _RE_PRICE_M.search(text)
    if m:
        try:
            return round(float(m.group(1).replace(",", ".")) * 1_000_000)
        except ValueError:
            pass
    m = _RE_PRICE.search(text)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    return None


def _match_stock(text: str) -> tuple[str, int] | None:
    """Fuzzy match d'un niveau de stock."""
    t = text.lower().strip()
    try:
        from rapidfuzz import fuzz
        best, best_score = None, 0
        for label, status in _STOCK_LEVELS:
            score = fuzz.ratio(t, label)
            if score > best_score:
                best_score, best = score, (label, status)
        return best if best and best_score >= 65 else None
    except ImportError:
        import difflib
        candidates = [lbl for lbl, _ in _STOCK_LEVELS]
        m = difflib.get_close_matches(t, candidates, n=1, cutoff=0.65)
        if m:
            for label, status in _STOCK_LEVELS:
                if label == m[0]:
                    return label, status
        return None


# ── Moteur ────────────────────────────────────────────────────────────────────

class TesseractEngine:
    def __init__(
        self,
        exe: Path | None = None,
        data_dir: Path | None = None,
        tessdata_dir: Path | None = None,
    ):
        self.exe          = exe          or _find_exe()
        self.data_dir     = data_dir     or _DEFAULT_DATA
        self.tessdata_dir = tessdata_dir or _DEFAULT_DATA

        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = str(self.exe)
            self._pt = pytesseract
        except ImportError as e:
            raise RuntimeError(
                "pytesseract non installé — pip install pytesseract"
            ) from e

    # ── Public ────────────────────────────────────────────────────────────────

    def extract_from_image(self, image_path: Path) -> "ScanResult | MissionResult | None":
        from PIL import Image, ImageOps

        try:
            Image.open(image_path).verify()  # vérifie lisibilité
        except Exception as e:
            raise RuntimeError(f"Impossible d'ouvrir l'image : {e}") from e

        # Détection du type d'écran
        screen_type = self.detect_screen_type(image_path)
        if screen_type == "mission":
            return self.extract_mission(image_path)

        img = Image.open(image_path)
        w, h = img.size

        # Zone 1 : nom du terminal — couvre le tiers gauche depuis le haut
        # (0.17 était trop bas pour "Starlight Station" et équivalents)
        term_img = img.crop((int(w * 0.01), int(h * 0.04), int(w * 0.45), int(h * 0.35)))
        term_img = ImageOps.invert(term_img.convert("L"))

        # Zone 2 : liste des commodités (panneau droit SHOP INVENTORY)
        list_img = img.crop((int(w * 0.58), int(h * 0.12), int(w * 0.99), int(h * 0.99)))
        list_img = ImageOps.invert(list_img.convert("L"))

        env_bak = os.environ.get("TESSDATA_PREFIX")
        os.environ["TESSDATA_PREFIX"] = str(self.tessdata_dir)
        try:
            terminal   = self._ocr_terminal(term_img)
            tsv        = self._ocr_tsv(list_img)
        except Exception as e:
            raise RuntimeError(f"Tesseract a échoué : {e}") from e
        finally:
            if env_bak is None:
                os.environ.pop("TESSDATA_PREFIX", None)
            else:
                os.environ["TESSDATA_PREFIX"] = env_bak

        lines       = self._tsv_to_lines(tsv)
        commodities = self._parse_commodity_lines(lines)

        # Détecter le mode depuis les lignes OCR
        mode = "sell" if any(
            re.search(r"(IN\s+DEMAND|SELLABLE\s+CARGO)", l, re.IGNORECASE)
            for l in lines
        ) else "buy"

        return ScanResult(
            terminal    = terminal or image_path.stem,
            commodities = commodities,
            source      = "ocr",
            mode        = mode,
        )

    # ── OCR interne ───────────────────────────────────────────────────────────

    def _ocr_terminal(self, img) -> str:
        """Lit le nom du terminal (panneau gauche). Essaie PSM 6 puis PSM 7."""
        known = self._load_words(self.data_dir / "terminals.user-words")
        for psm in (6, 7, 11):
            text = self._pt.image_to_string(
                img, lang="eng_sc", config=f"--psm {psm} --oem 3"
            ).strip()
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if not lines:
                continue
            if known:
                hit = self._fuzzy_best(lines, known, cutoff=65)
                if hit:
                    return hit
            # Retourne les deux premières lignes non-vides comme nom brut
            return " ".join(lines[:2])
        return ""

    def debug_terminal(self, image_path: Path) -> list[str]:
        """Retourne les lignes OCR brutes de la zone terminal (diagnostic)."""
        from PIL import Image, ImageOps
        img = Image.open(image_path)
        w, h = img.size
        term_img = img.crop((int(w * 0.01), int(h * 0.04), int(w * 0.45), int(h * 0.35)))
        term_img = ImageOps.invert(term_img.convert("L"))

        env_bak = os.environ.get("TESSDATA_PREFIX")
        os.environ["TESSDATA_PREFIX"] = str(self.tessdata_dir)
        try:
            lines = []
            for psm in (6, 7):
                text = self._pt.image_to_string(
                    term_img, lang="eng_sc", config=f"--psm {psm} --oem 3"
                ).strip()
                psm_lines = [l.strip() for l in text.splitlines() if l.strip()]
                lines.append(f"[PSM {psm}] " + " | ".join(psm_lines) if psm_lines else f"[PSM {psm}] (vide)")
            return lines
        finally:
            if env_bak is None:
                os.environ.pop("TESSDATA_PREFIX", None)
            else:
                os.environ["TESSDATA_PREFIX"] = env_bak

    def _ocr_tsv(self, img) -> dict:
        parts = ["--psm 11", "--oem 3"]  # sparse text, comme SC-Datarunner
        uw  = self.data_dir / "commodities.user-words"
        pat = self.data_dir / "sc.patterns"
        if uw.exists():
            parts.append(f'--user-words "{uw}"')
        if pat.exists():
            parts.append(f'--user-patterns "{pat}"')
        return self._pt.image_to_data(
            img,
            lang        = "eng_sc",
            config      = " ".join(parts),
            output_type = self._pt.Output.DICT,
        )

    # ── Construction des lignes depuis le TSV ─────────────────────────────────

    def _tsv_to_lines(self, tsv: dict) -> list[str]:
        """Regroupe les mots du TSV en lignes par proximité verticale adaptative."""
        words = []
        for i, text in enumerate(tsv["text"]):
            text = text.strip()
            if not text or int(tsv["conf"][i]) < 30:
                continue
            words.append((
                int(tsv["top"][i]),
                int(tsv["left"][i]),
                int(tsv["height"][i]),
                text,
            ))

        if not words:
            return []

        words.sort()  # (top, left, height, text)

        # Bande Y = 60 % de la hauteur médiane des mots (adapte à la résolution)
        heights = [h for _, _, h, _ in words if h > 3]
        band = max(6, int(statistics.median(heights) * 0.6)) if heights else 10

        lines: list[str] = []
        current_group = [words[0]]
        ref_top = words[0][0]

        for w in words[1:]:
            if abs(w[0] - ref_top) <= band:
                current_group.append(w)
            else:
                lines.append(" ".join(x[3] for x in sorted(current_group, key=lambda x: x[1])))
                current_group = [w]
                ref_top = w[0]

        lines.append(" ".join(x[3] for x in sorted(current_group, key=lambda x: x[1])))
        return lines

    def debug_lines(self, image_path: Path) -> list[str]:
        """Retourne les lignes OCR brutes (pour diagnostic /scan debug)."""
        from PIL import Image, ImageOps
        img = Image.open(image_path)
        w, h = img.size
        list_img = img.crop((int(w * 0.58), int(h * 0.12), int(w * 0.99), int(h * 0.99)))
        list_img = ImageOps.invert(list_img.convert("L"))

        env_bak = os.environ.get("TESSDATA_PREFIX")
        os.environ["TESSDATA_PREFIX"] = str(self.tessdata_dir)
        try:
            tsv = self._ocr_tsv(list_img)
        finally:
            if env_bak is None:
                os.environ.pop("TESSDATA_PREFIX", None)
            else:
                os.environ["TESSDATA_PREFIX"] = env_bak

        return self._tsv_to_lines(tsv)

    # ── Détection du type d'écran ─────────────────────────────────────────────

    def detect_screen_type(self, image_path: Path) -> str:
        """Détecte 'mission' | 'terminal' | 'unknown' en lisant l'en-tête."""
        from PIL import Image, ImageOps
        img = Image.open(image_path)
        w, h = img.size
        # Partie haute droite — onglets + premières infos
        probe = img.crop((int(w * 0.33), int(h * 0.04), int(w * 0.99), int(h * 0.30)))
        probe = ImageOps.invert(probe.convert("L"))
        env_bak = os.environ.get("TESSDATA_PREFIX")
        os.environ["TESSDATA_PREFIX"] = str(self.tessdata_dir)
        try:
            text = self._pt.image_to_string(
                probe, lang="eng_sc", config="--psm 6 --oem 3"
            ).upper()
        except Exception:
            text = ""
        finally:
            if env_bak is None:
                os.environ.pop("TESSDATA_PREFIX", None)
            else:
                os.environ["TESSDATA_PREFIX"] = env_bak

        m_score = sum(1 for kw in _MISSION_KEYWORDS if kw in text)
        t_score  = sum(1 for kw in _TERMINAL_KEYWORDS if kw in text)
        if m_score >= 2 and m_score > t_score:
            return "mission"
        if t_score > 0:
            return "terminal"
        return "unknown"

    # ── Extraction mission ─────────────────────────────────────────────────────

    def extract_mission(self, image_path: Path) -> MissionResult:
        """Extrait les données d'un screenshot de l'écran Contrats."""
        from PIL import Image, ImageOps
        img = Image.open(image_path)
        w, h = img.size

        def _ocr(crop_box, psm=6) -> str:
            region = img.crop(crop_box)
            region = ImageOps.invert(region.convert("L"))
            env_bak = os.environ.get("TESSDATA_PREFIX")
            os.environ["TESSDATA_PREFIX"] = str(self.tessdata_dir)
            try:
                return self._pt.image_to_string(
                    region, lang="eng_sc", config=f"--psm {psm} --oem 3"
                ).strip()
            except Exception:
                return ""
            finally:
                if env_bak is None:
                    os.environ.pop("TESSDATA_PREFIX", None)
                else:
                    os.environ["TESSDATA_PREFIX"] = env_bak

        # ── Onglet actif (OFFERS / ACCEPTED / HISTORY) ────────────────────────
        tab_text = _ocr((int(w*.33), int(h*.06), int(w*.75), int(h*.12)), psm=7)
        active_tab = ""
        for t in ("OFFERS", "ACCEPTED", "HISTORY"):
            if t.lower() in tab_text.lower():
                active_tab = t
                break

        # ── Titre (grand texte panneau droit) ─────────────────────────────────
        title_text = _ocr((int(w*.33), int(h*.12), int(w*.66), int(h*.23)), psm=6)
        title = " ".join(title_text.split())

        # ── Infos (Reward / Availability / Contracted By) ─────────────────────
        info_text = _ocr((int(w*.64), int(h*.11), int(w*.93), int(h*.25)), psm=6)
        reward, availability, contracted_by = self._parse_mission_info(info_text)

        # ── Détails (colonne gauche du contenu) ───────────────────────────────
        details_text = _ocr((int(w*.33), int(h*.25), int(w*.62), int(h*.86)), psm=4)

        # ── Objectifs (colonne droite) ────────────────────────────────────────
        objectives_text = _ocr((int(w*.62), int(h*.25), int(w*.93), int(h*.86)), psm=4)
        objectives = self._parse_objectives(objectives_text)
        parsed_objectives = self._parse_objectives_structured(objectives)

        # ── Liste missions panneau gauche ─────────────────────────────────────
        list_text = _ocr((int(w*.06), int(h*.06), int(w*.31), int(h*.88)), psm=4)
        mission_list = self._parse_mission_list(list_text)

        # ── Texte bleu (liens importants) ─────────────────────────────────────
        blue_text = self._extract_blue_text(img)

        return MissionResult(
            title=title,
            tab=active_tab,
            reward=reward,
            contract_availability=availability,
            contracted_by=contracted_by,
            details=details_text,
            objectives=objectives,
            parsed_objectives=parsed_objectives,
            blue_text=blue_text,
            mission_list=mission_list,
        )

    def _parse_mission_info(self, text: str) -> tuple[int, str, str]:
        """Parse le bloc Reward / Contract Availability / Contracted By."""
        reward = 0
        m = _RE_REWARD.search(text)
        if m:
            try:
                reward = int(m.group(1).replace(",", "").replace(" ", ""))
            except ValueError:
                pass

        availability = ""
        m = _RE_AVAIL.search(text)
        if m:
            availability = m.group(1).strip().split("\n")[0].strip()

        contracted_by = ""
        m = _RE_CONTRACTED.search(text)
        if m:
            contracted_by = m.group(1).strip().split("\n")[0].strip()

        return reward, availability, contracted_by

    def _parse_objectives(self, text: str) -> list[str]:
        """Extrait les objectifs de mission (lignes brutes, bullets supprimés)."""
        objectives = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if re.match(r"primary\s+obj", line, re.IGNORECASE):
                continue
            line_clean = _RE_BULLET.sub("", line).strip()
            if len(line_clean) > 5:
                objectives.append(line_clean)
        return objectives

    def _parse_objectives_structured(self, raw_lines: list[str]) -> list[ParsedObjective]:
        """Parse structurel des objectifs : Collect/Deliver → commodity, SCU, location."""
        results: list[ParsedObjective] = []
        pending: ParsedObjective | None = None

        for raw in raw_lines:
            # Nettoyer bullet + préfixes OCR parasites
            line = _RE_BULLET.sub("", raw).strip()
            line = _RE_OBJ_NOISE.sub("", line).strip()
            line = line.rstrip(".")

            if not line or len(line) < 4:
                continue
            if _RE_OBJ_UI.match(line):
                continue

            # ── Collect ──────────────────────────────────────────────────────
            m = _RE_OBJ_COLLECT.match(line)
            if m:
                if pending:
                    results.append(pending)
                loc_raw = m.group(2).strip()
                pending = ParsedObjective(
                    kind="collect",
                    commodity=m.group(1).strip().title(),
                    location=loc_raw,
                    raw=line,
                )
                continue

            # ── Deliver ──────────────────────────────────────────────────────
            m = _RE_OBJ_DELIVER.match(line)
            if m:
                if pending:
                    results.append(pending)
                qty = int(m.group(1))
                commodity = m.group(2).strip().title()
                location = m.group(3).strip() if m.group(3) else None
                hint = None
                if location:
                    # Format "above X" (cas le plus courant, onglet OFFERS)
                    m_above = _RE_OBJ_ABOVE.search(location)
                    if m_above:
                        hint = m_above.group(1).strip()
                        location = location[:m_above.start()].strip()
                    # Format "at X's L2 Lagrange point" (onglet ACCEPTED)
                    elif re.search(r"\s+at\s+", location, re.IGNORECASE):
                        m_at = _RE_OBJ_AT_LAGRANGE.search(location)
                        if m_at:
                            hint = m_at.group(1).strip()
                            location = location[:m_at.start()].strip()
                    # Ligne coupée : "Baijini Point above" — "above" traîne en fin
                    elif re.search(r"\babove\s*$", location, re.IGNORECASE):
                        location = re.sub(r"\s*\babove\s*$", "", location, flags=re.IGNORECASE).strip()
                pending = ParsedObjective(
                    kind="deliver",
                    commodity=commodity,
                    quantity_scu=qty,
                    location=location,
                    location_hint=hint,
                    raw=line,
                )
                continue

            # ── Ligne de continuation ─────────────────────────────────────────
            if pending:
                m_above = _RE_OBJ_ABOVE.search(line)
                if m_above:
                    pending.location_hint = m_above.group(1).strip()
                elif line.lower().startswith("above "):
                    pending.location_hint = line[6:].strip()
                elif pending.location is None:
                    # La localisation était coupée — cette ligne est la suite
                    pending.location = line
                # Sinon bruit OCR → ignorer

        if pending:
            results.append(pending)
        return results

    def _parse_mission_list(self, text: str) -> list[tuple[str, int]]:
        """Parse la liste des missions avec récompenses (ex. 'ALLIANCE AID... 40k')."""
        missions = []
        current_lines: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                if current_lines:
                    missions.append((" ".join(current_lines), 0))
                    current_lines = []
                continue
            m = _RE_MISSION_AMT.search(line)
            if m:
                amount_k = int(m.group(1))
                title_part = line[:line.rfind(m.group(0))].strip()
                current_lines.append(title_part)
                missions.append((" ".join(current_lines), amount_k * 1000))
                current_lines = []
            else:
                current_lines.append(line)
        if current_lines:
            missions.append((" ".join(current_lines), 0))
        return [m for m in missions if m[0].strip()]

    def _extract_blue_text(self, img) -> list[str]:
        """Extrait le texte en bleu (liens/lieux importants) par masque couleur."""
        from PIL import Image as PILImage, ImageOps

        img_rgb = img.convert("RGB")
        width, height = img_rgb.size

        # Masque bleu : B dominant, assez saturé
        try:
            import numpy as np
            arr = np.array(img_rgb, dtype=np.int32)
            R, G, B = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
            mask = (B > 100) & (B - R > 40) & (B - G > 15) & (B > 120)
            white = np.zeros((height, width), dtype=np.uint8)
            white[mask] = 255
            blue_img = PILImage.fromarray(white, mode="L")
        except ImportError:
            # Fallback PIL pur (lent mais fonctionnel)
            pixels = img_rgb.load()
            blue_img = PILImage.new("L", (width, height), 0)
            bp = blue_img.load()
            for y in range(height):
                for x in range(width):
                    r, g, b = pixels[x, y]
                    if b > 100 and (b - r) > 40 and (b - g) > 15 and b > 120:
                        bp[x, y] = 255

        # Dilater légèrement le masque pour améliorer l'OCR
        from PIL import ImageFilter
        blue_img = blue_img.filter(ImageFilter.MaxFilter(3))
        # Inverser pour Tesseract (texte noir sur fond blanc)
        blue_for_ocr = ImageOps.invert(blue_img)

        env_bak = os.environ.get("TESSDATA_PREFIX")
        os.environ["TESSDATA_PREFIX"] = str(self.tessdata_dir)
        try:
            text = self._pt.image_to_string(
                blue_for_ocr, lang="eng_sc", config="--psm 11 --oem 3"
            )
        except Exception:
            text = ""
        finally:
            if env_bak is None:
                os.environ.pop("TESSDATA_PREFIX", None)
            else:
                os.environ["TESSDATA_PREFIX"] = env_bak

        lines = [l.strip() for l in text.splitlines() if l.strip() and len(l.strip()) > 4]
        return lines

    def debug_mission(self, image_path: Path) -> dict:
        """Retourne toutes les zones OCR brutes d'un screenshot mission (pour /scan debug)."""
        from PIL import Image, ImageOps
        img = Image.open(image_path)
        w, h = img.size

        def _ocr_raw(crop_box, psm=6) -> str:
            region = img.crop(crop_box)
            region = ImageOps.invert(region.convert("L"))
            env_bak = os.environ.get("TESSDATA_PREFIX")
            os.environ["TESSDATA_PREFIX"] = str(self.tessdata_dir)
            try:
                return self._pt.image_to_string(
                    region, lang="eng_sc", config=f"--psm {psm} --oem 3"
                ).strip()
            except Exception:
                return "(erreur OCR)"
            finally:
                if env_bak is None:
                    os.environ.pop("TESSDATA_PREFIX", None)
                else:
                    os.environ["TESSDATA_PREFIX"] = env_bak

        return {
            "onglets":       _ocr_raw((int(w*.33), int(h*.06), int(w*.75), int(h*.12)), 7),
            "titre":         _ocr_raw((int(w*.33), int(h*.12), int(w*.66), int(h*.23)), 6),
            "info_bloc":     _ocr_raw((int(w*.64), int(h*.11), int(w*.93), int(h*.25)), 6),
            "details":       _ocr_raw((int(w*.33), int(h*.25), int(w*.62), int(h*.86)), 4),
            "objectifs":     _ocr_raw((int(w*.62), int(h*.25), int(w*.93), int(h*.86)), 4),
            "liste_gauche":  _ocr_raw((int(w*.06), int(h*.06), int(w*.31), int(h*.88)), 4),
            "texte_bleu":    "\n".join(self._extract_blue_text(img)),
        }

    # ── Machine à états : NOM → SCU → STOCK → PRIX ───────────────────────────

    def _parse_commodity_lines(self, lines: list[str]) -> list[ScannedCommodity]:
        known    = self._load_words(self.data_dir / "commodities.user-words")
        result:  list[ScannedCommodity] = []
        current: ScannedCommodity | None = None
        pending_qty: int | None = None   # SCU peut arriver AVANT le nom dans l'OCR
        in_demand_section: bool = False  # True après détection INDEMAND

        for raw in lines:
            line = raw.strip()
            if not line or _SKIP_NOISE_RE.match(line):
                continue

            # ── Détection de section avant le skip ────────────────────────────
            if _SECTION_SELLABLE_RE.match(line):
                in_demand_section = False
            elif _SECTION_INDEMAND_RE.match(line):
                in_demand_section = True

            if _SKIP_STARTS_RE.match(line):
                continue

            # ── Prix + stock (TOUJOURS prioritaires, jamais noms) ─────────────
            price = _parse_price(line)
            # Isoler le texte avant ¤/ø pour le match stock (évite dilution du ratio)
            line_for_stock = re.split(r"[¤ø]", line)[0].strip()
            stock = _match_stock(line_for_stock)

            if price is not None or stock is not None:
                if current:
                    if price is not None and not current.price:
                        current.price = price
                    if stock is not None and not current.stock:
                        current.stock, current.stock_status = stock
                continue   # toujours — empêche "INVENTORY"/"STOCK" d'être noms

            # ── SCU seul sur sa ligne ("859 SCU") ─────────────────────────────
            m = _RE_SCU.match(line)
            if m:
                try:
                    qty = int(m.group(1).replace(",", ""))
                except ValueError:
                    qty = None
                if qty is not None:
                    if current and current.quantity is None:
                        current.quantity = qty
                    elif current is None:
                        pending_qty = qty   # SCU avant le nom : on bufferise
                continue

            # ── Nom de commodité ──────────────────────────────────────────────
            # 1. Supprimer préfixe parasite OCR : "e DISTILLED" → "DISTILLED"
            _words = line.split()
            line_clean = " ".join(_words[1:]) if len(_words) >= 2 and len(_words[0]) <= 2 else line
            # 2. Supprimer suffixe UI : "WASTE SHOP QUANTITY" → "WASTE"
            line_clean = _RE_UI_SUFFIX.sub("", line_clean).strip() or line_clean
            name = self._fuzzy_commodity(line_clean, known)
            if name:
                if current:
                    result.append(current)
                c = ScannedCommodity(name=name, in_demand=in_demand_section)
                # SCU parfois sur la même ligne que le nom ("STIMS 1,012 SCU")
                m2 = _RE_SCU_INLINE.search(line)
                if m2:
                    try:
                        c.quantity = int(m2.group(1).replace(",", ""))
                    except ValueError:
                        pass
                # Appliquer le SCU bufferisé si pas déjà trouvé en inline
                if c.quantity is None and pending_qty is not None:
                    c.quantity = pending_qty
                pending_qty = None
                current = c

        if current:
            result.append(current)
        return result

    # ── Fuzzy matching ────────────────────────────────────────────────────────

    def _fuzzy_best(self, candidates: list[str], known: list[str], cutoff: int) -> str:
        try:
            from rapidfuzz import fuzz
            best, score = "", 0
            for c in candidates:
                for k in known:
                    s = fuzz.partial_ratio(c.upper(), k.upper())
                    if s > score:
                        score, best = s, k
            return best if score >= cutoff else ""
        except ImportError:
            import difflib
            for c in candidates:
                m = difflib.get_close_matches(c, known, n=1, cutoff=cutoff / 100)
                if m:
                    return m[0]
            return ""

    def _fuzzy_commodity(self, line: str, known: list[str]) -> str | None:
        if not known or re.match(r"^[\d\s,./()~\"\'\\]+$", line) or len(line) < 3:
            return None
        ku = [k.upper() for k in known]
        try:
            from rapidfuzz import process, fuzz
            # 1. Ligne complète
            r = process.extractOne(
                line.upper(), ku, scorer=fuzz.WRatio, score_cutoff=75,
            )
            if r:
                return known[ku.index(r[0])]
            # 2. Fallback mot par mot — "STINS 1,012 SCU" → "STINS" → "STIMS"
            for word in line.split():
                if len(word) <= 3 or re.match(r"^[\d,./]+$", word):
                    continue
                r2 = process.extractOne(word.upper(), ku, scorer=fuzz.WRatio, score_cutoff=80)
                if r2:
                    return known[ku.index(r2[0])]
        except ImportError:
            import difflib
            # 1. Ligne complète
            m = difflib.get_close_matches(line.upper(), ku, n=1, cutoff=0.60)
            if m:
                for k in known:
                    if k.upper() == m[0]:
                        return k
            # 2. Mot par mot — seuil abaissé 0.75 pour typos OCR (STINS→STIMS)
            for word in line.split():
                if len(word) <= 3 or re.match(r"^[\d,./]+$", word):
                    continue
                m2 = difflib.get_close_matches(word.upper(), ku, n=1, cutoff=0.75)
                if m2:
                    for k in known:
                        if k.upper() == m2[0]:
                            return k
        return None

    # ── Utilitaires ───────────────────────────────────────────────────────────

    def _load_words(self, path: Path) -> list[str]:
        if not path.exists():
            return []
        with open(path, encoding="utf-8", errors="replace") as f:
            return [
                l.strip() for l in f
                if l.strip() and not l.strip().isdigit() and len(l.strip()) > 3
            ]
