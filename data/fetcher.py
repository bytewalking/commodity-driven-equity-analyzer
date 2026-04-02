"""Data fetching module with akshare + BaoStock backends, SQLite cache, and synthetic fallback."""

import warnings
warnings.filterwarnings("ignore")

import random
import time

import numpy as np
import pandas as pd
import streamlit as st

from data.cache import (
    get_commodity, update_commodity,
    get_stock, update_stock,
    coverage,
)

# Minimum cache coverage to skip a live fetch (80% of business days present)
_CACHE_THRESHOLD = 0.8

# Stock exchange prefix map for BaoStock (code → "sh.XXXXXX" / "sz.XXXXXX")
_BS_PREFIX = {
    "6": "sh",  # Shanghai: 60xxxx, 601xxx…
    "0": "sz",  # Shenzhen: 000xxx, 002xxx…
    "3": "sz",  # ChiNext:  300xxx
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_commodity(futures_symbol: str, start_date: str, end_date: str) -> tuple:
    """Return (DataFrame[price], source_label, error_msg).

    Priority: akshare → local cache → synthetic data.
    """
    errors = []

    # 1. Try akshare
    try:
        import akshare as ak
        df = ak.futures_main_sina(symbol=futures_symbol)
        if df is not None and not df.empty:
            date_col = df.columns[0]
            close_col = df.columns[4]
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.set_index(date_col)[[close_col]].rename(columns={close_col: "price"})
            df = _filter_dates(df, start_date, end_date).dropna()
            if not df.empty:
                update_commodity(futures_symbol, df)
                return df, "akshare", None
        errors.append("futures_main_sina: 返回空数据")
    except Exception as e:
        errors.append(f"futures_main_sina: {e}")

    # AL0 secondary akshare attempt
    if futures_symbol == "AL0":
        try:
            import akshare as ak
            df = ak.futures_zh_daily_sina(symbol=futures_symbol)
            if df is not None and not df.empty:
                date_col = "date" if "date" in df.columns else df.columns[0]
                close_col = "close" if "close" in df.columns else df.columns[4]
                df[date_col] = pd.to_datetime(df[date_col])
                df = df.set_index(date_col)[[close_col]].rename(columns={close_col: "price"})
                df = _filter_dates(df, start_date, end_date).dropna()
                if not df.empty:
                    update_commodity(futures_symbol, df)
                    return df, "akshare", None
            errors.append("futures_zh_daily_sina: 返回空数据")
        except Exception as e:
            errors.append(f"futures_zh_daily_sina: {e}")

    # 2. Fall back to local cache
    cached = get_commodity(futures_symbol, start_date, end_date)
    if not cached.empty:
        return cached, "本地缓存", " | ".join(errors)

    # 3. Synthetic data
    return _synthetic_commodity(futures_symbol, start_date, end_date), "模拟数据", " | ".join(errors)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_stock(stock_code: str, start_date: str, end_date: str) -> tuple:
    """Return (DataFrame[price], source_label, error_msg).

    Priority: local cache (if sufficient) → akshare → BaoStock → stale cache → synthetic.
    """
    errors = []

    # 1. Serve from cache if coverage is sufficient
    cached = get_stock(stock_code, start_date, end_date)
    if coverage(cached, start_date, end_date) >= _CACHE_THRESHOLD:
        return cached, "本地缓存", None

    # Randomized delay to avoid rate limiting on live requests
    time.sleep(random.uniform(0.5, 1.5))

    # 2. Try akshare (eastmoney)
    try:
        import akshare as ak
        df = ak.stock_zh_a_hist(
            symbol=stock_code, period="daily",
            start_date=start_date, end_date=end_date, adjust="qfq",
        )
        if df is not None and not df.empty:
            df["日期"] = pd.to_datetime(df["日期"])
            df = df.set_index("日期")[["收盘"]].rename(columns={"收盘": "price"})
            df = df.dropna()
            if not df.empty:
                update_stock(stock_code, df)
                return df, "akshare", None
        errors.append("stock_zh_a_hist: 返回空数据")
    except Exception as e:
        errors.append(f"stock_zh_a_hist: {e}")

    # 3. Try BaoStock
    try:
        df = _fetch_baostock(stock_code, start_date, end_date)
        if df is not None and not df.empty:
            update_stock(stock_code, df)
            return df, "baostock", None
        errors.append("baostock: 返回空数据")
    except Exception as e:
        errors.append(f"baostock: {e}")

    # 4. Stale cache (any data available)
    if not cached.empty:
        return cached, "本地缓存（旧）", " | ".join(errors)

    # 5. Synthetic
    return _synthetic_stock(stock_code, start_date, end_date), "模拟数据", " | ".join(errors)


# ---------------------------------------------------------------------------
# BaoStock helper
# ---------------------------------------------------------------------------

def _fetch_baostock(stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    import baostock as bs

    prefix = _BS_PREFIX.get(stock_code[0], "sh")
    bs_code = f"{prefix}.{stock_code}"

    # BaoStock expects YYYY-MM-DD
    s = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}" if len(start_date) == 8 else start_date
    e = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}" if len(end_date) == 8 else end_date

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock login failed: {lg.error_msg}")
    try:
        rs = bs.query_history_k_data_plus(
            bs_code, "date,close",
            start_date=s, end_date=e,
            frequency="d", adjustflag="2",  # 前复权
        )
        rows = [r for r in rs.data if r[1]]
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["date", "price"])
        df["date"] = pd.to_datetime(df["date"])
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        return df.set_index("date").dropna()
    finally:
        bs.logout()


# ---------------------------------------------------------------------------
# Synthetic data generators (last-resort fallback)
# ---------------------------------------------------------------------------

_BASE_PRICES = {
    "AL0": 18_000,
    "AU0": 600,
}

_STOCK_BASES = {
    # 铝
    "601600": 6.5,  "600219": 12.0, "000807": 8.2,
    "000933": 10.0, "002532": 15.0, "601677": 18.5,
    # 黄金
    "601899": 12.0, "600547": 45.0, "600489": 8.0,
    "002155": 8.5,  "601069": 20.0, "600988": 25.0,
}

_COMMODITY_SEEDS = {"AL0": 1, "AU0": 2}

_STOCK_COMMODITY_MAP = {
    # 铝
    "601600": "AL0", "600219": "AL0", "000807": "AL0",
    "000933": "AL0", "002532": "AL0", "601677": "AL0",
    # 黄金
    "601899": "AU0", "600547": "AU0", "600489": "AU0",
    "002155": "AU0", "601069": "AU0", "600988": "AU0",
}


def _business_dates(start_date: str, end_date: str) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start_date, end=end_date)


def _filter_dates(df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    s, e = pd.to_datetime(start_date), pd.to_datetime(end_date)
    return df[(df.index >= s) & (df.index <= e)]


def _gbm(n: int, base: float, mu: float, sigma: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    returns = rng.normal(mu, sigma * np.sqrt(1), n)
    return base * np.exp(np.cumsum(returns))


def _synthetic_commodity(futures_symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    dates = _business_dates(start_date, end_date)
    seed = _COMMODITY_SEEDS.get(futures_symbol, 99)
    base = _BASE_PRICES.get(futures_symbol, 10_000)
    prices = _gbm(len(dates), base, mu=0.0001, sigma=0.012, seed=seed)
    return pd.DataFrame({"price": prices}, index=dates)


def _synthetic_stock(stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    dates = _business_dates(start_date, end_date)
    n = len(dates)
    base = _STOCK_BASES.get(stock_code, 15.0)

    comm_symbol = _STOCK_COMMODITY_MAP.get(stock_code, "AL0")
    comm_seed = _COMMODITY_SEEDS.get(comm_symbol, 1)
    rng_comm = np.random.default_rng(comm_seed)
    comm_factor = rng_comm.normal(0, 0.012, n)

    stock_seed = abs(hash(stock_code)) % (2**31)
    rng_idio = np.random.default_rng(stock_seed)
    idio = rng_idio.normal(0.0001, 0.014, n)

    beta = 0.55
    combined = beta * comm_factor + np.sqrt(1 - beta**2) * idio
    prices = base * np.exp(np.cumsum(combined))
    return pd.DataFrame({"price": prices}, index=dates)
