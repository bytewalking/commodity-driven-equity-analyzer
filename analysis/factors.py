"""Factor calculation: correlation, spread, z-score, lead-lag."""

import numpy as np
import pandas as pd


def align(commodity: pd.DataFrame, stock: pd.DataFrame) -> pd.DataFrame:
    """Inner-join commodity and stock on date index, returning 2-column DataFrame."""
    df = pd.concat([commodity["price"], stock["price"]], axis=1, join="inner")
    df.columns = ["commodity", "stock"]
    return df.dropna()


def log_returns(aligned: pd.DataFrame) -> pd.DataFrame:
    return np.log(aligned).diff().dropna()


def rolling_correlation(aligned: pd.DataFrame, window: int = 60) -> pd.Series:
    """Rolling Pearson correlation of log-returns."""
    lr = log_returns(aligned)
    return lr["commodity"].rolling(window=window).corr(lr["stock"])


def overall_correlation(aligned: pd.DataFrame) -> float:
    """Full-period Pearson correlation of log-returns."""
    lr = log_returns(aligned)
    if lr.empty or lr["commodity"].std() == 0 or lr["stock"].std() == 0:
        return 0.0
    return float(lr["commodity"].corr(lr["stock"]))


def spread(aligned: pd.DataFrame) -> pd.Series:
    """Normalized spread: both series rebased to 100, then differenced."""
    norm_comm = aligned["commodity"] / aligned["commodity"].iloc[0] * 100
    norm_stock = aligned["stock"] / aligned["stock"].iloc[0] * 100
    return norm_comm - norm_stock


def rolling_zscore(spread_series: pd.Series, window: int = 60) -> pd.Series:
    """Rolling z-score of spread."""
    mu = spread_series.rolling(window=window).mean()
    sigma = spread_series.rolling(window=window).std()
    return (spread_series - mu) / sigma


def lead_lag(aligned: pd.DataFrame, max_lag: int = 10) -> dict:
    """
    Cross-correlation at lags -max_lag … +max_lag.

    Positive lag k means commodity leads stock by k days:
        corr(commodity[t-k], stock[t])
    Negative lag k means stock leads commodity by |k| days.
    """
    lr = log_returns(aligned)
    comm = lr["commodity"]
    stk = lr["stock"]

    corrs = {}
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            c = comm.shift(lag).corr(stk)
        else:
            c = comm.corr(stk.shift(-lag))
        corrs[lag] = float(c) if not np.isnan(c) else 0.0

    best = max(corrs, key=lambda k: abs(corrs[k]))
    return {
        "correlations": corrs,
        "best_lag": best,
        "best_corr": corrs[best],
        "interpretation": _interpret(best),
    }


def _interpret(lag: int) -> str:
    if lag > 0:
        return f"商品价格领先股价 {lag} 天"
    elif lag < 0:
        return f"股价领先商品价格 {abs(lag)} 天"
    return "同步变动（无明显领先滞后）"


def volatility_annualized(prices: pd.Series) -> float:
    """Annualized volatility from daily log-returns."""
    lr = np.log(prices).diff().dropna()
    return float(lr.std() * np.sqrt(252))


def score_stock(corr: float, ann_vol: float, current_zscore: float) -> float:
    """Composite relevance score 0-100 for ranking."""
    corr_score = abs(corr) * 60
    vol_score = max(0.0, 20.0 - ann_vol * 50)   # reward lower vol up to a point
    signal_score = max(0.0, 20.0 - abs(current_zscore) * 4)  # closer to mean → lower urgency
    return round(corr_score + vol_score + signal_score, 1)
