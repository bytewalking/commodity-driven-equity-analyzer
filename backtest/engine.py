"""Z-score mean-reversion backtesting engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any


def run(
    stock_prices: pd.Series,
    zscore: pd.Series,
    buy_threshold: float = -2.0,
    sell_threshold: float = 2.0,
    stop_loss: float = -0.05,
    initial_capital: float = 100_000.0,
) -> dict[str, Any]:
    """
    Simulate a long-only Z-score mean-reversion strategy.

    Buy  when z-score crosses below `buy_threshold`.
    Sell when z-score crosses above `sell_threshold` OR stop-loss hit.

    Returns dict with keys: portfolio, trades, metrics, aligned_prices.
    """
    aligned = pd.concat([stock_prices, zscore], axis=1, join="inner").dropna()
    aligned.columns = ["price", "zscore"]

    position = 0
    entry_price = 0.0
    cash = initial_capital
    shares = 0.0

    portfolio_values: list[dict] = []
    trades: list[dict] = []

    for date, row in aligned.iterrows():
        price: float = row["price"]
        z: float = row["zscore"]

        if position == 1:
            unrealized = (price - entry_price) / entry_price

            # --- exit: normal sell takes priority over stop-loss ---
            if z > sell_threshold:
                ret = (price - entry_price) / entry_price
                cash = shares * price
                shares = 0.0
                position = 0
                trades.append(_trade_record(date, "卖出", price, ret, z,
                    f"Z-Score {z:.2f} 突破卖出阈值 {sell_threshold:.2f}，价差回归"))
                entry_price = 0.0

            # --- stop-loss ---
            elif unrealized < stop_loss:
                cash = shares * price
                shares = 0.0
                position = 0
                trades.append(_trade_record(date, "止损卖出", price, unrealized, z,
                    f"浮亏 {unrealized:.2%}，触发止损线 {stop_loss:.2%}"))
                entry_price = 0.0

        # --- entry: not on the same bar as an exit ---
        last_trade_date = trades[-1]["date"] if trades else None
        if position == 0 and z < buy_threshold and last_trade_date != date:
            shares = cash / price
            cash = 0.0
            position = 1
            entry_price = price
            trades.append(_trade_record(date, "买入", price, 0.0, z,
                f"Z-Score {z:.2f} 低于买入阈值 {buy_threshold:.2f}，股票累积涨幅历史性偏低"))

        portfolio_values.append({"date": date, "value": cash + shares * price})

    # Close open position at end
    if position == 1 and len(aligned):
        last_price = aligned["price"].iloc[-1]
        last_date = aligned.index[-1]
        ret = (last_price - entry_price) / entry_price
        cash = shares * last_price
        trades.append(_trade_record(last_date, "收盘平仓", last_price, ret, aligned["zscore"].iloc[-1],
            "回测结束，强制平仓"))
        if portfolio_values:
            portfolio_values[-1]["value"] = cash

    portfolio = (
        pd.DataFrame(portfolio_values)
        .set_index("date")
        if portfolio_values
        else pd.DataFrame(columns=["value"])
    )
    portfolio["returns"] = portfolio["value"].pct_change()

    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame(
        columns=["date", "type", "price", "return", "zscore", "reason"]
    )

    return {
        "portfolio": portfolio,
        "trades": trades_df,
        "metrics": _metrics(portfolio, trades, initial_capital),
        "aligned_prices": aligned["price"],
    }


def _trade_record(date, t: str, price: float, ret: float, z: float, reason: str = "") -> dict:
    return {"date": date, "type": t, "price": round(price, 4),
            "return": round(ret, 6), "zscore": round(z, 4), "reason": reason}


def _metrics(portfolio: pd.DataFrame, trades: list, initial_capital: float) -> dict:
    if portfolio.empty:
        return {}

    final_value = portfolio["value"].iloc[-1]
    total_return = (final_value - initial_capital) / initial_capital

    days = (portfolio.index[-1] - portfolio.index[0]).days
    years = max(days / 365.0, 1e-6)
    annual_return = (1 + total_return) ** (1 / years) - 1

    daily_ret = portfolio["returns"].dropna()
    sharpe = (
        (daily_ret.mean() / daily_ret.std() * np.sqrt(252))
        if len(daily_ret) > 1 and daily_ret.std() > 0
        else 0.0
    )

    rolling_max = portfolio["value"].cummax()
    drawdown = (portfolio["value"] - rolling_max) / rolling_max
    max_drawdown = drawdown.min()

    exits = [t for t in trades if t["type"] in ("卖出", "止损卖出", "收盘平仓")]
    win_rate = (
        sum(1 for t in exits if t["return"] > 0) / len(exits)
        if exits else 0.0
    )
    calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

    return {
        "total_return": round(total_return, 6),
        "annual_return": round(annual_return, 6),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_drawdown, 6),
        "win_rate": round(win_rate, 4),
        "calmar": round(calmar, 4),
        "total_trades": len(exits),
        "final_value": round(final_value, 2),
    }
