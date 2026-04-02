# Commodity-driven Equity Analyzer

A Streamlit application for quantitative analysis, strategy backtesting, and monitoring of A-share stocks driven by commodity futures price factors.

[中文文档 README_CN.md](README_CN.md)

---

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## Project Structure

```
app.py                  # Main entry point, UI and page routing
config.py               # Commodity/stock static config, default strategy params
data/
  fetcher.py            # Data layer (akshare → BaoStock → local cache → synthetic)
  cache.py              # SQLite local price cache
analysis/
  factors.py            # Factor calculation (correlation, spread, Z-Score, lead-lag, regression)
backtest/
  engine.py             # Z-Score mean-reversion backtest engine
monitor/
  watchlist.py          # Watchlist persistence (JSON)
  notifier.py           # Email signal notifications (SMTP SSL)
```

---

## Features

### Home
- Auto-matches related stocks for the selected commodity
- Calculates full-period correlation, annualized volatility, current Z-Score
- Composite ranking score (correlation 60pts + volatility 20pts + Z-Score deviation 20pts)
- Displays current buy/sell signals

### Factor Analysis
- **Price comparison**: both series normalized to 100, comparing relative performance
- **Rolling correlation**: Pearson correlation coefficient over a rolling window
- **Spread Z-Score**: standard deviations of current spread from historical mean
- **Lead-lag analysis**: cross-correlation to determine which series leads
- **Regression analysis**: OLS fit of Y = aX + b with five statistical metrics

### Strategy Backtest
- Z-Score mean-reversion strategy, long-only
- Configurable buy/sell thresholds, stop-loss ratio, and initial capital
- Outputs equity curve, max drawdown, Sharpe ratio, win rate, etc.

### Monitor
- Persistent watchlist with signal refresh
- Email push notifications via SMTP (QQ Mail, 163, Gmail, etc.)

---

## Data Sources

Four-tier fallback chain:

```
akshare (live) → BaoStock (fallback) → Local SQLite cache → Synthetic data (last resort)
```

| Tier | Description |
|------|-------------|
| akshare | Commodity: SHFE/DCE/CZCE continuous contracts via Sina; Stock: Eastmoney daily, forward-adjusted |
| BaoStock | Free A-share historical data, no token required, better network compatibility |
| Local cache | SQLite stores previously fetched data; works offline after first successful fetch |
| Synthetic | GBM-simulated prices, **for UI continuity only — not suitable for research** |

Data source is clearly labeled in the UI: 🟢 Live / 🔵 Cached / 🟡 Synthetic.

### Covered Instruments

| Commodity | Futures Symbol | Related Stocks |
|-----------|---------------|----------------|
| Aluminum | AL0 (SHFE continuous) | Chalco, Nanshan Aluminum, Yunnan Aluminum, Shenghuo, Tianshan Aluminum, Mingtai Aluminum |
| Gold | AU0 (SHFE continuous) | Zijin Mining, Shandong Gold, CNGC Gold, Hunan Gold, Tibet Gold, Chifeng Gold |

---

## Factor Formulas

### Normalized Price

$$P^*_t = \frac{P_t}{P_0} \times 100$$

Both commodity and stock prices are normalized to a common base (= 100 at the start date) to eliminate unit differences and compare relative performance directly.

### Rolling Correlation

$$\rho_t = \text{Pearson}(r^C_{t-N+1:t},\ r^S_{t-N+1:t})$$

At each trading day, computes the Pearson correlation of log-returns over the past N days. Default N = 60 days (~3 months).

**Window size guide:**

| Window | Characteristics | Use case |
|--------|----------------|----------|
| 20–40 days | Sensitive, noisy | Short-term |
| 60 days (default) | Balanced | Medium-term |
| 90–120 days | Smooth, lagging signals | Medium/long-term |

### Spread Z-Score

$$\text{Spread}_t = P^{C*}_t - P^{S*}_t$$

$$Z_t = \frac{\text{Spread}_t - \mu_t}{\sigma_t}$$

Measures how many standard deviations the current spread is from its rolling historical mean.

| Z-Score | Meaning | Signal |
|---------|---------|--------|
| < −2 | Stock relatively undervalued | 🟢 Buy |
| > +2 | Stock relatively overvalued | 🔴 Sell |
| −2 to +2 | Normal range | Hold |

### Lead-Lag Analysis

$$\rho(k) = \text{Corr}(r^C_{t-k},\ r^S_t), \quad k \in [-10, +10]$$

| k | Meaning |
|---|---------|
| k > 0 | Commodity leads stock by k days |
| k < 0 | Stock leads commodity by \|k\| days |
| k = 0 | Synchronous movement |

### Regression Analysis (OLS)

$$Y = aX + b$$

$$a = \frac{\text{Cov}(X, Y)}{\text{Var}(X)}, \quad b = \bar{Y} - a\bar{X}$$

- X: commodity daily log-return
- Y: stock daily log-return

| Output | Meaning |
|--------|---------|
| Coefficient (a) | Slope: expected stock return per 1% commodity move |
| Constant (b) | Intercept: baseline daily return independent of commodity |
| Std Error | Standard error of slope estimate; smaller = more precise |
| P-value | < 0.05 indicates statistically significant relationship |
| R-squared | Fraction of stock return variance explained by commodity |

---

## Backtest Strategy

**Type**: Z-Score mean-reversion, long-only

**Trading logic:**

```
Each trading day:
  If in position:
    Z-Score > sell threshold  → Normal sell (takes priority)
    Unrealized loss < stop-loss → Stop-loss sell
  If flat AND Z-Score < buy threshold AND no trade executed today → Buy
```

**Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| Buy Z-Score threshold | −2.0 | Enter long when Z-Score drops below this value |
| Sell Z-Score threshold | +2.0 | Exit long when Z-Score rises above this value |
| Z-Score window | 60 days | Lookback period for spread mean and std |
| Stop-loss ratio | −5% | Force exit if unrealized loss exceeds this |
| Initial capital | ¥100,000 | Starting cash for equity curve calculation |

**Performance metrics:**

| Metric | Formula | Description |
|--------|---------|-------------|
| Total return | $(V_{end} - V_0) / V_0$ | Cumulative return over full period |
| Annual return | $(1+R)^{1/T}-1$ | Annualized equivalent return |
| Sharpe ratio | $\bar{r}_d / \sigma_d \times \sqrt{252}$ | Return per unit of risk; > 1 is good |
| Max drawdown | Peak-to-trough decline | Worst-case loss from any high point |
| Win rate | Profitable trades / total trades | Probability of profit per trade |

---

## Email Notifications

Configure SMTP in the Monitor tab to receive signal alerts by email.

**QQ Mail example:**
1. Log in to QQ Mail web → Settings → Account → Enable SMTP service
2. Generate an authorization code (16-character string, not your login password)
3. Enter in the Monitor tab: server `smtp.qq.com`, port `465`, use the authorization code as password

No fees required — sends via your own email account.

---

## Disclaimer

This tool is for research and educational purposes only and does not constitute investment advice. Past backtest results do not guarantee future performance.
