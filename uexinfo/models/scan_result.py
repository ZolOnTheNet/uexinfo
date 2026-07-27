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
    # Confiance OCR minimale (0-100) parmi les champs extraits par SC-Datarunner
    # (nom/quantité/stock/prix) — 100 = pas de donnée de confiance disponible
    # (ancien format de log, ou scan OCR direct d'uexinfo).
    confidence: int = 100


@dataclass
class ScanResult:
    terminal: str
    timestamp: datetime = field(default_factory=datetime.now)
    commodities: list[ScannedCommodity] = field(default_factory=list)
    source: str = "ocr"     # "ocr" | "log"
    mode: str = "buy"       # "buy" = IN STOCK (achat) | "sell" = IN DEMAND / SELLABLE CARGO (vente)
    validated: bool = False  # True = soumis à l'API UEX par l'utilisateur (données confirmées)
    image_path: str = ""     # Chemin absolu du screenshot source (source="ocr" uniquement)
