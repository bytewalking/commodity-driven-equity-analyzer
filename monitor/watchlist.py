"""Persistent watchlist backed by a local JSON file."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

_store_dir = os.environ.get("WATCHLIST_DIR", os.path.join(os.path.dirname(__file__), ".."))
WATCHLIST_PATH = os.path.join(_store_dir, "watchlist.json")


def _load() -> list[dict[str, Any]]:
    if os.path.exists(WATCHLIST_PATH):
        try:
            with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save(data: list[dict[str, Any]]) -> None:
    with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def load() -> list[dict[str, Any]]:
    return _load()


def add(
    commodity: str,
    stock_code: str,
    stock_name: str,
    strategy_params: dict,
) -> bool:
    """Add entry; returns False if already exists."""
    data = _load()
    for item in data:
        if item["commodity"] == commodity and item["stock_code"] == stock_code:
            return False
    data.append(
        {
            "commodity": commodity,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "strategy_params": strategy_params,
            "added_at": datetime.now().isoformat(),
            "last_signal": None,
            "last_zscore": None,
            "last_checked": None,
        }
    )
    _save(data)
    return True


def remove(commodity: str, stock_code: str) -> bool:
    data = _load()
    new = [d for d in data if not (d["commodity"] == commodity and d["stock_code"] == stock_code)]
    if len(new) < len(data):
        _save(new)
        return True
    return False


def update_signal(commodity: str, stock_code: str, signal: str | None, zscore: float) -> None:
    data = _load()
    for item in data:
        if item["commodity"] == commodity and item["stock_code"] == stock_code:
            item["last_signal"] = signal
            item["last_zscore"] = round(zscore, 4)
            item["last_checked"] = datetime.now().isoformat()
    _save(data)
