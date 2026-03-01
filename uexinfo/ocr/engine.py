"""Moteur OCR Tesseract — Mode B."""
from __future__ import annotations

from pathlib import Path

from uexinfo.models.scan_result import ScannedCommodity, ScanResult

_BASE = Path(__file__).parents[2] / "extprg" / "SC-Datarunner-UEX"

_DEFAULT_EXE       = _BASE / "dep" / "Tesseract-OCR" / "tesseract.exe"
_DEFAULT_DATA      = _BASE / "data"
_DEFAULT_TESSDATA  = _BASE / "data"   # eng_sc.traineddata se trouve dans data/


class TesseractEngine:
    def __init__(
        self,
        exe: Path | None = None,
        data_dir: Path | None = None,
        tessdata_dir: Path | None = None,
    ):
        self.exe = exe or _DEFAULT_EXE
        self.data_dir = data_dir or _DEFAULT_DATA
        self.tessdata_dir = tessdata_dir or _DEFAULT_TESSDATA

        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = str(self.exe)
            self._pytesseract = pytesseract
        except ImportError as e:
            raise RuntimeError(
                "pytesseract n'est pas installé. "
                "Installez-le avec : pip install pytesseract"
            ) from e

    def extract_from_image(self, image_path: Path) -> ScanResult | None:
        """Extrait les données du terminal depuis une capture d'écran.

        1. Ouvre l'image avec PIL
        2. Lance Tesseract avec eng_sc + fichiers de patterns SC
        3. Parse le texte brut → terminal + commodités
        4. Retourne ScanResult(source="ocr")
        """
        try:
            from PIL import Image
            img = Image.open(image_path)
        except Exception as e:
            raise RuntimeError(f"Impossible d'ouvrir l'image : {e}") from e

        user_words = self.data_dir / "commodities.user-words"
        patterns   = self.data_dir / "sc.patterns"

        # Passer le dossier tessdata via la variable d'environnement
        # (évite les problèmes de guillemets dans les args CLI sur Windows)
        import os
        env_backup = os.environ.get("TESSDATA_PREFIX")
        os.environ["TESSDATA_PREFIX"] = str(self.tessdata_dir)

        config_parts = ["--psm 11", "--oem 3"]
        if user_words.exists():
            config_parts.append(f'--user-words "{user_words}"')
        if patterns.exists():
            config_parts.append(f'--user-patterns "{patterns}"')

        config_str = " ".join(config_parts)

        try:
            text = self._pytesseract.image_to_string(
                img,
                lang="eng_sc",
                config=config_str,
            )
        except Exception as e:
            raise RuntimeError(f"Tesseract a échoué : {e}") from e
        finally:
            if env_backup is None:
                os.environ.pop("TESSDATA_PREFIX", None)
            else:
                os.environ["TESSDATA_PREFIX"] = env_backup

        terminal, commodities = self._parse_ocr_text(text)
        if not terminal:
            terminal = image_path.stem  # fallback sur le nom de fichier

        return ScanResult(
            terminal=terminal,
            commodities=commodities,
            source="ocr",
        )

    def _parse_ocr_text(self, text: str) -> tuple[str, list[ScannedCommodity]]:
        """Extrait le nom de terminal et les commodités depuis le texte OCR brut."""
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        terminal = self._match_terminal(lines)
        commodities = self._match_commodities(lines)

        return terminal, commodities

    def _match_terminal(self, lines: list[str]) -> str:
        """Fuzzy match du nom de terminal depuis les premières lignes."""
        # Charger la liste des noms de terminaux connus
        terminal_words_path = self.data_dir / "terminals.user-words"
        known: list[str] = []
        if terminal_words_path.exists():
            with open(terminal_words_path, encoding="utf-8", errors="replace") as f:
                known = [l.strip() for l in f if l.strip()]

        if not known:
            return lines[0] if lines else ""

        # Chercher dans les premières lignes le meilleur match
        candidates = lines[:10]
        best_name = ""
        best_score = 0

        try:
            from rapidfuzz import fuzz
            for line in candidates:
                for name in known:
                    score = fuzz.partial_ratio(line.upper(), name.upper())
                    if score > best_score:
                        best_score = score
                        best_name = name
        except ImportError:
            import difflib
            for line in candidates:
                matches = difflib.get_close_matches(line, known, n=1, cutoff=0.6)
                if matches:
                    return matches[0]

        return best_name if best_score >= 70 else (lines[0] if lines else "")

    def _match_commodities(self, lines: list[str]) -> list[ScannedCommodity]:
        """Extrait les noms de commodités depuis le texte OCR.

        Retourne une liste minimale (name seulement) — pas de prix ni stock
        sans parseur de layout avancé.
        """
        commodity_words_path = self.data_dir / "commodities.user-words"
        known: list[str] = []
        if commodity_words_path.exists():
            with open(commodity_words_path, encoding="utf-8", errors="replace") as f:
                known = [l.strip() for l in f if l.strip()]

        if not known:
            return []

        found: list[ScannedCommodity] = []
        seen: set[str] = set()

        try:
            from rapidfuzz import process, fuzz
            for line in lines:
                result = process.extractOne(
                    line, known, scorer=fuzz.WRatio, score_cutoff=80
                )
                if result and result[0] not in seen:
                    seen.add(result[0])
                    found.append(ScannedCommodity(name=result[0]))
        except ImportError:
            import difflib
            for line in lines:
                matches = difflib.get_close_matches(line, known, n=1, cutoff=0.8)
                if matches and matches[0] not in seen:
                    seen.add(matches[0])
                    found.append(ScannedCommodity(name=matches[0]))

        return found
