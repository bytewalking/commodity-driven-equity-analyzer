"""Data fetching module with akshare backend and synthetic fallback."""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_commodity(futures_symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Return daily commodity close prices as DataFrame with column 'price'."""
    try:
        import akshare as ak
        df = ak.futures_main_sina(symbol=futures_symbol)
        if df is not None and not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")[["close"]].rename(columns={"close": "price"})
            df = _filter_dates(df, start_date, end_date).dropna()
            if not df.empty:
                return df
    except Exception:
        pass
    return _synthetic_commodity(futures_symbol, start_date, end_date)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_stock(stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Return daily stock close prices as DataFrame with column 'price'."""
    try:
        import akshare as ak
        df = ak.stock_zh_a_hist(
            symbol=stock_code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
        if df is not None and not df.empty:
            df["日期"] = pd.to_datetime(df["日期"])
            df = df.set_index("日期")[["收盘"]].rename(columns={"收盘": "price"})
            df = df.dropna()
            if not df.empty:
                return df
    except Exception:
        pass
    return _synthetic_stock(stock_code, start_date, end_date)


# ---------------------------------------------------------------------------
# Synthetic data generators (fallback)
# ---------------------------------------------------------------------------

_BASE_PRICES = {
    "AL0": 18_000,
    "ZC0": 800,
    "CU0": 65_000,
    "SC0": 550,
}

_STOCK_BASES = {
    "601600": 6.5,  "000807": 8.2,  "600219": 12.0, "601677": 18.5,
    "601088": 30.0, "600188": 22.5, "601225": 18.0, "601898": 8.0,
    "000983": 12.0, "600362": 14.0, "000630": 5.5,  "601168": 9.5,
    "601857": 7.0,  "600028": 6.0,
}

# Shared "market factor" seeds so stocks are loosely correlated with commodity
_COMMODITY_SEEDS = {"AL0": 1, "ZC0": 2, "CU0": 3, "SC0": 4}

_STOCK_COMMODITY_MAP = {
    "601600": "AL0", "000807": "AL0", "600219": "AL0", "601677": "AL0",
    "601088": "ZC0", "600188": "ZC0", "601225": "ZC0", "601898": "ZC0", "000983": "ZC0",
    "600362": "CU0", "000630": "CU0", "601168": "CU0",
    "601857": "SC0", "600028": "SC0",
}


def _business_dates(start_date: str, end_date: str) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start_date, end=end_date)


def _filter_dates(df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    s, e = pd.to_datetime(start_date), pd.to_datetime(end_date)
    return df[(df.index >= s) & (df.index <= e)]


def _gbm(n: int, base: float, mu: float, sigma: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    dt = 1
    returns = rng.normal(mu * dt, sigma * np.sqrt(dt), n)
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

    # Correlated factor from commodity
    comm_symbol = _STOCK_COMMODITY_MAP.get(stock_code, "AL0")
    comm_seed = _COMMODITY_SEEDS.get(comm_symbol, 1)
    rng_comm = np.random.default_rng(comm_seed)
    comm_factor = rng_comm.normal(0, 0.012, n)

    # Idiosyncratic component
    stock_seed = abs(hash(stock_code)) % (2**31)
    rng_idio = np.random.default_rng(stock_seed)
    idio = rng_idio.normal(0.0001, 0.014, n)

    beta = 0.55
    combined = beta * comm_factor + np.sqrt(1 - beta**2) * idio
    prices = base * np.exp(np.cumsum(combined))
    return pd.DataFrame({"price": prices}, index=dates)
