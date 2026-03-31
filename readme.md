# Commodity-driven Equity Analyzer
### 商品因子驱动股票分析平台

A quantitative research platform that discovers, measures, and monitors the statistical relationship between Chinese commodity futures prices and A-share equities. Users can rank stocks by commodity correlation, run z-score mean-reversion backtests, and receive daily trading signals via email — all through a browser-based UI.

---

## Features

| Module | Description |
|--------|-------------|
| **Stock Matching** | Ranks related A-shares by a composite score (correlation × volatility × z-score distance) |
| **Factor Analysis** | Rolling correlation, normalized spread, z-score, and lead-lag cross-correlation charts |
| **Strategy Backtest** | Long-only z-score mean-reversion with configurable thresholds, stop-loss, and rolling window |
| **Performance Metrics** | Total return, annualized return, Sharpe ratio, max drawdown, win rate, Calmar ratio |
| **Watchlist** | Persistent JSON-backed monitor list with one-click signal refresh |
| **Email Alerts** | SMTP signal dispatch with HTML/plain-text email when z-score thresholds are breached |

**Supported commodities:** Aluminum (铝) · Coal (煤炭) · Copper (铜) · Crude Oil (原油)

---

## Technology Stack

| Layer | Library / Tool |
|-------|---------------|
| UI | [Streamlit](https://streamlit.io) 1.28+ |
| Market data | [akshare](https://akshare.akfamily.xyz) (A-shares + SHFE/DCE/CZCE/INE futures) |
| Numerics | pandas · NumPy · SciPy |
| Charts | Plotly (interactive) |
| Notifications | Python `smtplib` (SMTP over SSL) |
| Containerization | Docker (multi-stage) · Docker Compose |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        app.py  (Streamlit)                  │
│                                                             │
│  ┌──────────┐  ┌───────────────┐  ┌──────────┐  ┌───────┐  │
│  │  首页    │  │  因子分析     │  │ 策略回测 │  │ 监控  │  │
│  │  Home    │  │  Analysis     │  │ Backtest │  │Monitor│  │
│  └────┬─────┘  └───────┬───────┘  └─────┬────┘  └───┬───┘  │
└───────┼────────────────┼────────────────┼────────────┼──────┘
        │                │                │            │
        ▼                ▼                ▼            ▼
┌───────────────┐ ┌──────────────┐ ┌──────────┐ ┌──────────────┐
│ data/         │ │ analysis/    │ │ backtest/│ │ monitor/     │
│ fetcher.py    │ │ factors.py   │ │ engine.py│ │ watchlist.py │
│               │ │              │ │          │ │ notifier.py  │
│ akshare API   │ │ correlation  │ │ z-score  │ │ JSON store   │
│  + GBM        │ │ spread       │ │ signals  │ │ SMTP email   │
│  fallback     │ │ z-score      │ │ metrics  │ │              │
│               │ │ lead-lag     │ │          │ │              │
└───────────────┘ └──────────────┘ └──────────┘ └──────────────┘
        │
        ▼
  akshare (live)
  ─────────────
  SHFE  AL0 / CU0
  CZCE  ZC0
  INE   SC0
  A-share daily (qfq-adjusted)
```

Data flows left-to-right: **fetch → align → factor calculation → signal → backtest / alert**.

---

## Project Structure

```
Commodity-driven Equity Analyzer/
├── app.py                  # Streamlit entry point; all UI and page routing
├── config.py               # Commodity definitions, stock mappings, default params
├── requirements.txt
├── Dockerfile              # Multi-stage build (builder + slim runtime)
├── docker-compose.yml
├── .dockerignore
├── .streamlit/
│   └── config.toml         # Server settings, CORS, theme
│
├── data/
│   └── fetcher.py          # fetch_commodity() / fetch_stock()
│                           # → tries akshare, falls back to synthetic GBM
│
├── analysis/
│   └── factors.py          # rolling_correlation · spread · rolling_zscore
│                           # lead_lag · volatility_annualized · score_stock
│
├── backtest/
│   └── engine.py           # run() → portfolio DataFrame + trades + metrics
│
├── monitor/
│   ├── watchlist.py        # add / remove / update_signal (watchlist.json)
│   └── notifier.py         # send_signals() via SMTP SSL
│
└── watchlist.json          # Auto-created; persisted via Docker volume
```

---

## How It Works

### 1. Data Layer (`data/fetcher.py`)

`fetch_commodity` and `fetch_stock` are decorated with `@st.cache_data(ttl=3600)`, so each symbol is fetched at most once per hour per session.

- **Primary source:** akshare — `futures_main_sina(symbol)` for continuous futures contracts; `stock_zh_a_hist(symbol, adjust="qfq")` for forward-adjusted A-share prices.
- **Fallback:** If akshare fails (network issue, API change), a correlated Geometric Brownian Motion series is generated deterministically from the ticker seed, so all downstream features remain functional for demo/dev purposes.

### 2. Factor Calculations (`analysis/factors.py`)

All calculations operate on aligned DataFrames (inner join on business dates).

| Factor | Method |
|--------|--------|
| **Correlation** | Pearson correlation of daily log-returns over a rolling window (default 60 days) |
| **Spread** | Both series rebased to 100 at the start of the window; spread = `norm_commodity − norm_stock` |
| **Z-Score** | `(spread − rolling_mean) / rolling_std` — measures how many standard deviations the spread has deviated from its recent mean |
| **Lead-Lag** | Cross-correlation of log-returns at integer lags `−10 … +10`; positive lag = commodity leads stock |

**Composite score** used for stock ranking:

```
score = |correlation| × 60   +   max(0, 20 − annualized_vol × 50)
                              +   max(0, 20 − |current_z| × 4)
```

### 3. Backtesting Engine (`backtest/engine.py`)

Simulates a **long-only, fully-invested** mean-reversion strategy:

```
Buy  → when z-score crosses below  buy_threshold  (default −2.0)
Sell → when z-score crosses above  sell_threshold (default +2.0)
      OR unrealized return < stop_loss           (default −5%)
```

Position sizing: 100% of available capital at each entry (single stock, no leverage).

Performance metrics computed:

| Metric | Formula |
|--------|---------|
| Annualized return | `(1 + total_return)^(365/days) − 1` |
| Sharpe ratio | `mean(daily_ret) / std(daily_ret) × √252` |
| Max drawdown | `min((value − rolling_max) / rolling_max)` |
| Win rate | `winning_exits / total_exits` |
| Calmar ratio | `annual_return / |max_drawdown|` |

### 4. Monitoring & Alerts (`monitor/`)

`watchlist.json` is a flat JSON array. Each entry records the commodity, stock code, strategy parameters, last signal, last z-score, and last check timestamp.

Email notifications are sent via `smtplib.SMTP_SSL`. The message is dual-part (plain text + HTML table) and is triggered manually from the Monitor tab or can be wired to a cron/scheduler externally.

---

## Quick Start

### Local

```bash
# 1. Install dependencies (Python 3.10+)
pip install -r requirements.txt

# 2. Run
streamlit run app.py
# Open http://localhost:8501
```

### Docker Compose (recommended for NAS)

```bash
# Build image and start in background
docker compose up -d --build

# View logs
docker compose logs -f

# Stop
docker compose down
```

The app will be available at `http://<host-ip>:8501`.

`watchlist.json` is stored in a named Docker volume (`watchlist_data`) and persists across container restarts and image rebuilds.

---

## Configuration

### Commodity & Stock Mapping (`config.py`)

Add new commodities by extending `COMMODITY_CONFIG`:

```python
"锌 (Zinc)": {
    "futures_symbol": "ZN0",   # akshare continuous contract symbol
    "color": "#17BECF",
    "unit": "元/吨",
    "related_stocks": [
        {"code": "000362", "name": "西部矿业", "industry": "有色金属-锌"},
    ],
},
```

### Default Strategy (`config.py`)

```python
DEFAULT_STRATEGY = {
    "buy_threshold":  -2.0,   # z-score buy signal
    "sell_threshold":  2.0,   # z-score sell signal
    "stop_loss":      -0.05,  # -5% hard stop
    "zscore_window":   60,    # rolling window in trading days
}
```

### Email Notifications

Configure SMTP credentials in the **监控 → 邮件通知配置** section of the UI. Tested with QQ Mail (`smtp.qq.com:465`) and Gmail (`smtp.gmail.com:465`). Use an app-specific password, not your account password.

### Docker Port

Edit the left-hand port in `docker-compose.yml` to avoid conflicts with other services on your NAS:

```yaml
ports:
  - "8888:8501"   # host:container
```

---

## Limitations

- **Data quality:** Results depend entirely on the accuracy of akshare data. Gaps or adjustments in the source data directly affect factor calculations.
- **Overfitting risk:** Z-score thresholds are not optimized; the default ±2σ is a common starting point, not a validated parameter.
- **Long-only:** The backtest does not support short positions or pairs trading.
- **Single-asset:** Each backtest covers one commodity–stock pair. Portfolio-level analysis is not implemented.
- **Past ≠ future:** All backtest results are historical simulations and do not predict future returns.

---

## Disclaimer

This tool is intended for quantitative research and educational purposes only. It does not constitute investment advice. Always conduct your own due diligence before making any investment decisions.
