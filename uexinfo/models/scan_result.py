"""Modèles résultat de scan — ScanResult et ScannedCommodity."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScannedCommodity:
    name: str
    commodity_id: int = 0
    quantity: int | None = None
    stock: str = ""
    stock_status: int = 0   # 1=out, 2=très bas, 3=bas, 4=moyen, 5=haut, 7=max
    price: int = 0          # aUEC/SCU
    in_demand: bool = False  # True = section INDEMAND (terminal veut mais joueur n'a pas)
    # Confiance OCR par champ (0-100), capturée depuis le nouveau format de
    # log SC-Datarunner — 100 = pas de donnée disponible (ancien format,
    # scan OCR direct d'uexinfo, ou champ recalculé/corrigé après coup).
    name_confidence: int = 100
    quantity_confidence: int = 100
    stock_confidence: int = 100
    price_confidence: int = 100
    # Signaux calculés après extraction (règles de gestion, pas l'OCR lui-même) :
    price_corrected: bool = False     # prix auto-corrigé (chiffre en trop / ×10 / vide → UEX)
    quantity_corrected: bool = False  # quantité plafonnée au max SCU déjà vu par UEX à ce terminal
    stock_corrected: bool = False     # stock forcé "out of stock" car quantité scannée = 0
    # True = ce mode (achat/vente) n'existe pas pour cette commodité à ce
    # terminal d'après UEX — signe probable d'une mauvaise détection de
    # terminal, de mode, ou de nom de commodité par l'OCR.
    terminal_mismatch: bool = False
    # True = scan validé (envoyé à UEX) mais UEX n'a encore aucune donnée
    # récente pour cette commodité précise — la valeur affichée reste celle
    # de l'OCR d'origine (potentiellement corrigée par l'utilisateur dans
    # Datarunner avant l'envoi, mais cette correction n'est jamais visible
    # dans le log ; seule l'API UEX, une fois à jour, la révèle).
    uex_pending: bool = False

    @property
    def confidence(self) -> int:
        """Confiance globale = la plus basse des confiances par champ (résumé)."""
        return min(self.name_confidence, self.quantity_confidence,
                   self.stock_confidence, self.price_confidence)


@dataclass
class ScanResult:
    terminal: str
    timestamp: datetime = field(default_factory=datetime.now)
    commodities: list[ScannedCommodity] = field(default_factory=list)
    source: str = "ocr"     # "ocr" | "log"
    mode: str = "buy"       # "buy" = IN STOCK (achat) | "sell" = IN DEMAND / SELLABLE CARGO (vente)
    validated: bool = False  # True = soumis à l'API UEX par l'utilisateur (données confirmées)
    image_path: str = ""     # Chemin absolu du screenshot source (source="ocr" uniquement)
