"""Stockage persistant des prix collectés par scan du joueur.

Les données sont fusionnées dans les rows UEX lors de l'affichage des terminaux.
Elles sont prioritaires sur les données UEX et distinguées par le flag _player=True.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import appdirs

from uexinfo.models.scan_result import ScanResult

_STORE_FILE = Path(appdirs.user_data_dir("uexinfo")) / "scan_prices.json"
_MAX_AGE_DAYS = 30  # données > 30 jours ignorées


class ScanPriceStore:
    """Lit/écrit les prix scannés par le joueur dans un fichier JSON persistant."""

    # ── I/O ───────────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if _STORE_FILE.exists():
            try:
                with open(_STORE_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _write(self, data: dict) -> None:
        _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── Écriture ──────────────────────────────────────────────────────────────

    def save_result(self, result: ScanResult, terminal_key: str = "") -> None:
        """Persiste les prix d'un ScanResult dans le store."""
        data = self._load()
        term_key = terminal_key or result.terminal.lower().strip()
        if term_key not in data:
            data[term_key] = {}

        is_sell = result.mode == "sell"
        # Utiliser le timestamp du scan (log/OCR) et non l'heure courante
        scan_ts = result.timestamp.timestamp() if hasattr(result.timestamp, 'timestamp') else time.time()

        for sc in result.commodities:
            # Prix 0 non validé → on ne surcharge pas les données existantes
            if not sc.price and not result.validated:
                continue

            cid_key = str(sc.commodity_id) if sc.commodity_id else f"name:{sc.name.lower()}"
            entry = data[term_key].get(cid_key, {})

            entry["commodity_name"] = sc.name
            entry["commodity_id"] = sc.commodity_id
            entry["timestamp"] = scan_ts
            entry["validated"] = result.validated

            if is_sell:
                if sc.price:
                    entry["price_sell"] = sc.price
                entry["status_sell"] = sc.stock_status
                if sc.quantity is not None:
                    entry["scu_sell_stock"] = sc.quantity
                    existing_max = entry.get("scu_sell_max") or 0
                    if sc.quantity > existing_max:
                        entry["scu_sell_max"] = sc.quantity
            else:
                if sc.price:
                    entry["price_buy"] = sc.price
                entry["status_buy"] = sc.stock_status
                if sc.quantity is not None:
                    entry["scu_buy"] = sc.quantity

            data[term_key][cid_key] = entry

        self._write(data)

    # ── Lecture ───────────────────────────────────────────────────────────────

    def get_rows(self, terminal_key: str) -> list[dict]:
        """Retourne les enregistrements de prix scannés pour un terminal."""
        data = self._load()
        entries = data.get(terminal_key, {})
        cutoff = time.time() - (_MAX_AGE_DAYS * 86400)
        return [e for e in entries.values() if e.get("timestamp", 0) >= cutoff]

    # ── Modification ─────────────────────────────────────────────────────────

    def update_entry(self, terminal_key: str, cid_key: str, **fields) -> bool:
        """Met à jour des champs d'une entrée. Retourne True si trouvé."""
        data = self._load()
        term = data.get(terminal_key, {})
        if cid_key not in term:
            return False
        term[cid_key].update({k: v for k, v in fields.items() if v is not None})
        data[terminal_key] = term
        self._write(data)
        return True

    def delete_entry(self, terminal_key: str, cid_key: str) -> bool:
        """Supprime une entrée. Retourne True si elle existait."""
        data = self._load()
        term = data.get(terminal_key, {})
        if cid_key not in term:
            return False
        del term[cid_key]
        if term:
            data[terminal_key] = term
        else:
            del data[terminal_key]
        self._write(data)
        return True

    def delete_field(self, terminal_key: str, cid_key: str, *field_names) -> bool:
        """Supprime des champs d'une entrée (ex: price_buy). Retourne True si trouvé."""
        data = self._load()
        term = data.get(terminal_key, {})
        if cid_key not in term:
            return False
        for f in field_names:
            term[cid_key].pop(f, None)
        data[terminal_key] = term
        self._write(data)
        return True

    def list_terminal(self, terminal_key: str) -> dict[str, dict]:
        """Retourne {cid_key: entry} pour un terminal."""
        return self._load().get(terminal_key, {})

    def migrate_keys(self, ctx) -> int:
        """Convertit les clés nom-terminal → str(terminal_id). Retourne nb migrations."""
        from uexinfo.cli.commands.info import _loc
        data = self._load()
        changed = 0
        terminals = ctx.cache.terminals if ctx.cache else []
        id_map: dict[str, str] = {}  # old_key → new_key
        for t in terminals:
            loc_key  = _loc(t.name).lower()
            full_key = t.name.lower()
            new_key  = str(t.id)
            for old in (loc_key, full_key):
                if old in data and old != new_key:
                    id_map[old] = new_key
        for old, new in id_map.items():
            existing = data.get(new, {})
            existing.update(data.pop(old))
            data[new] = existing
            changed += 1
        if changed:
            self._write(data)
        return changed

    # ── Fusion ────────────────────────────────────────────────────────────────

    def merge_into(self, uex_rows: list[dict], terminal_key: str) -> list[dict]:
        """Fusionne les données scan dans les rows UEX.

        Les prix scanné remplacent les champs correspondants dans les rows UEX.
        Les commodités scan absentes du cache UEX sont ajoutées comme rows synthétiques.
        Les rows résultantes ont _player=True sur les champs issus du scan.
        """
        scan_rows = self.get_rows(terminal_key)
        if not scan_rows:
            return uex_rows

        # Index scan par commodity_id et par nom — si doublon, prendre le plus récent
        scan_by_id:   dict[int, dict] = {}
        scan_by_name: dict[str, dict] = {}
        for r in scan_rows:
            cid = r.get("commodity_id") or 0
            if cid:
                existing = scan_by_id.get(cid)
                if not existing or r.get("timestamp", 0) >= existing.get("timestamp", 0):
                    scan_by_id[cid] = r
            cname = (r.get("commodity_name") or "").lower()
            if cname:
                existing = scan_by_name.get(cname)
                if not existing or r.get("timestamp", 0) >= existing.get("timestamp", 0):
                    scan_by_name[cname] = r

        matched_cids:   set[int] = set()
        matched_cnames: set[str] = set()
        result: list[dict] = []

        for row in uex_rows:
            cid   = int(row.get("id_commodity") or 0)
            cname = (row.get("commodity_name") or "").lower()
            # Si doublon id/nom, prendre le plus récent
            r_by_id   = scan_by_id.get(cid)
            r_by_name = scan_by_name.get(cname)
            if r_by_id and r_by_name and r_by_id is not r_by_name:
                scan_r = r_by_id if r_by_id.get("timestamp", 0) >= r_by_name.get("timestamp", 0) else r_by_name
            else:
                scan_r = r_by_id or r_by_name

            if scan_r:
                merged = dict(row)
                if scan_r.get("price_buy"):
                    merged["price_buy"]  = scan_r["price_buy"]
                    merged["status_buy"] = scan_r.get("status_buy", row.get("status_buy"))
                    merged["_player_buy"] = True
                if scan_r.get("price_sell"):
                    merged["price_sell"]  = scan_r["price_sell"]
                    merged["status_sell"] = scan_r.get("status_sell", row.get("status_sell"))
                    merged["_player_sell"] = True
                if scan_r.get("scu_buy") is not None:
                    merged["scu_buy"] = scan_r["scu_buy"]
                # scu_sell_stock : observation courante (compat : ancien format stockait dans scu_sell_max)
                scan_stock = scan_r.get("scu_sell_stock")
                if scan_stock is None and scan_r.get("scu_sell_max") is not None:
                    scan_stock = scan_r["scu_sell_max"]
                if scan_stock is not None:
                    merged["scu_sell_stock"] = scan_stock
                # scu_sell_max : capacité = max(high-water scan, capacité UEX)
                scan_max = scan_r.get("scu_sell_max") or 0
                uex_max  = row.get("scu_sell_max") or 0
                best_max = max(scan_max, uex_max)
                if best_max:
                    merged["scu_sell_max"] = best_max
                merged["_scan_ts"]   = scan_r.get("timestamp", 0)
                merged["_validated"] = scan_r.get("validated", False)
                result.append(merged)
                matched_cids.add(cid)
                matched_cnames.add(cname)
            else:
                result.append(row)

        # Commodités scannées absentes du cache UEX → rows synthétiques
        for r in scan_rows:
            cid   = r.get("commodity_id") or 0
            cname = (r.get("commodity_name") or "").lower()
            if cid in matched_cids or cname in matched_cnames:
                continue
            synthetic: dict = {
                "id_commodity":   cid,
                "commodity_name": r.get("commodity_name", ""),
                "price_buy":      r.get("price_buy", 0),
                "price_sell":     r.get("price_sell", 0),
                "status_buy":     r.get("status_buy", 0),
                "status_sell":    r.get("status_sell", 0),
                "scu_buy":        r.get("scu_buy"),
                "scu_sell_stock": r.get("scu_sell_stock") if r.get("scu_sell_stock") is not None else r.get("scu_sell_max"),
                "scu_sell_max":   r.get("scu_sell_max") or 0,
                "_player_buy":    bool(r.get("price_buy")),
                "_player_sell":   bool(r.get("price_sell")),
                "_scan_ts":       r.get("timestamp", 0),
                "_validated":     r.get("validated", False),
            }
            result.append(synthetic)

        return result
