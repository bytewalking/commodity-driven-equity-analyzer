"""SQLite-backed local price cache.

Stores commodity and stock daily close prices so that previously fetched
data survives akshare failures across sessions.
"""

from __future__ import annotations

import os
import sqlite3

import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), "market_cache.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commodity_prices (
            symbol TEXT,
            date   TEXT,
            price  REAL,
            PRIMARY KEY (symbol, date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_prices (
            code  TEXT,
            date  TEXT,
            price REAL,
            PRIMARY KEY (code, date)
        )
    """)
    conn.commit()
    return conn


def _read(table: str, key_col: str, key: str, start: str, end: str) -> pd.DataFrame:
    with _conn() as conn:
        df = pd.read_sql_query(
            f"SELECT date, price FROM {table} WHERE {key_col}=? AND date>=? AND date<=? ORDER BY date",
            conn, params=(key, start[:10].replace("", "-") if len(start) == 8 else start, end[:10]),
        )
    if df.empty:
        return pd.DataFrame(columns=["price"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def _write(table: str, key_col: str, key: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    rows = [(key, str(d.date()), float(p)) for d, p in zip(df.index, df["price"])]
    with _conn() as conn:
        conn.executemany(
            f"INSERT OR REPLACE INTO {table} ({key_col}, date, price) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()


def _normalize_date(d: str) -> str:
    """Convert YYYYMMDD or YYYY-MM-DD to YYYY-MM-DD."""
    d = d.strip()
    if len(d) == 8 and "-" not in d:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


def get_commodity(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    return _read("commodity_prices", "symbol", symbol,
                 _normalize_date(start_date), _normalize_date(end_date))


def update_commodity(symbol: str, df: pd.DataFrame) -> None:
    _write("commodity_prices", "symbol", symbol, df)


def get_stock(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    return _read("stock_prices", "code", code,
                 _normalize_date(start_date), _normalize_date(end_date))


def update_stock(code: str, df: pd.DataFrame) -> None:
    _write("stock_prices", "code", code, df)


def coverage(cached: pd.DataFrame, start_date: str, end_date: str) -> float:
    """Return fraction of business days in [start, end] covered by cache."""
    if cached.empty:
        return 0.0
    expected = len(pd.bdate_range(start=start_date, end=end_date))
    if expected == 0:
        return 1.0
    return min(len(cached) / expected, 1.0)
