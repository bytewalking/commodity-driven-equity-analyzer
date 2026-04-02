"""
商品因子驱动股票分析平台
Commodity-driven Equity Analyzer

Run:  streamlit run app.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st
from datetime import date

from config import COMMODITY_CONFIG, DEFAULT_STRATEGY, DEFAULT_START, DEFAULT_END
from data.fetcher import fetch_commodity, fetch_stock
from analysis import factors as fac
from backtest import engine as bt
from monitor import watchlist as wl
from monitor import notifier


# ============================================================
# Page config
# ============================================================

st.set_page_config(
    page_title="商品因子驱动股票分析平台",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# Sidebar – global controls
# ============================================================

with st.sidebar:
    st.title("📊 商品因子分析平台")
    st.divider()

    commodity_name = st.selectbox(
        "选择商品",
        options=list(COMMODITY_CONFIG.keys()),
        key="commodity_name",
    )
    cfg = COMMODITY_CONFIG[commodity_name]

    st.subheader("日期范围")
    col_s, col_e = st.columns(2)
    with col_s:
        start_input = st.date_input("开始", value=date(2015, 1, 1), key="date_start")
    with col_e:
        end_input = st.date_input("结束", value=date.today(), key="date_end")

    start_str = start_input.strftime("%Y%m%d")
    end_str = end_input.strftime("%Y%m%d")

    st.divider()
    st.caption("数据来源: akshare（失败时自动切换为模拟数据）")
    st.caption("⚠️ 本工具仅供研究，不构成投资建议")


# ============================================================
# Helper: load commodity data (cached per selection)
# ============================================================

@st.cache_data(show_spinner=False)
def _commodity(symbol: str, s: str, e: str) -> tuple:
    return fetch_commodity(symbol, s, e)


@st.cache_data(show_spinner=False)
def _stock(code: str, s: str, e: str) -> tuple:
    return fetch_stock(code, s, e)


def load_commodity() -> tuple:
    return _commodity(cfg["futures_symbol"], start_str, end_str)


def load_stock(code: str) -> tuple:
    return _stock(code, start_str, end_str)


def _src_badge(src: str) -> str:
    return {
        "akshare":    "🟢 akshare 实时数据",
        "baostock":   "🟢 BaoStock 实时数据",
        "本地缓存":    "🔵 本地缓存数据",
        "本地缓存（旧）": "🟠 本地缓存（旧）",
    }.get(src, "🟡 模拟数据（所有数据源失败）")


def _show_src(label: str, src: str, err: str | None) -> None:
    """Display data source caption; if failed, show error in expander."""
    st.caption(f"{label}：{_src_badge(src)}")
    if err:
        with st.expander("查看失败原因"):
            st.code(err, language=None)


# ============================================================
# Tabs
# ============================================================

TAB_HOME, TAB_ANALYSIS, TAB_BACKTEST, TAB_MONITOR = st.tabs(
    ["🏠 首页", "📈 因子分析", "🔄 策略回测", "👁️ 监控"]
)


# ============================================================
# TAB 1 – HOME
# ============================================================

with TAB_HOME:
    st.header(f"商品：{commodity_name}")
    st.markdown("根据选定商品，自动匹配相关股票并评分排名。")

    with st.spinner("正在加载数据并计算相关性…"):
        comm_df, comm_src, comm_err = load_commodity()

        rows = []
        synthetic_stocks = []
        stock_errors = {}
        for stock_info in cfg["related_stocks"]:
            code = stock_info["code"]
            name = stock_info["name"]
            industry = stock_info["industry"]

            stk_df, stk_src, stk_err = load_stock(code)
            if stk_src == "模拟数据":
                synthetic_stocks.append(name)
            if stk_err:
                stock_errors[name] = stk_err
            aligned = fac.align(comm_df, stk_df)

            if aligned.empty or len(aligned) < 30:
                continue

            corr = fac.overall_correlation(aligned)
            vol = fac.volatility_annualized(aligned["stock"])
            cr_res = fac.cumret_spread_zscore(aligned)
            current_z = float(cr_res["zscore"].dropna().iloc[-1]) if not cr_res["zscore"].dropna().empty else 0.0

            signal = None
            if current_z < DEFAULT_STRATEGY["buy_threshold"]:
                signal = "🟢 买入"
            elif current_z > DEFAULT_STRATEGY["sell_threshold"]:
                signal = "🔴 卖出"

            score = fac.score_stock(corr, vol, current_z)

            rows.append(
                {
                    "股票代码": code,
                    "股票名称": name,
                    "行业": industry,
                    "相关性": round(corr, 4),
                    "年化波动率": f"{vol:.1%}",
                    "当前 Z-Score": round(current_z, 2),
                    "当前信号": signal or "—",
                    "综合评分": score,
                    "数据来源": {"akshare": "🟢 实时", "baostock": "🟢 实时", "本地缓存": "🔵 缓存", "本地缓存（旧）": "🟠 旧缓存"}.get(stk_src, "🟡 模拟"),
                }
            )

    if rows:
        df_rank = pd.DataFrame(rows).sort_values("综合评分", ascending=False).reset_index(drop=True)
        df_rank.index += 1

        # Data source banners
        _show_src("商品数据", comm_src, comm_err)
        if synthetic_stocks:
            st.warning(f"以下股票使用模拟数据（akshare 获取失败）：{', '.join(synthetic_stocks)}")
            if stock_errors:
                with st.expander("查看股票获取失败原因"):
                    for sname, serr in stock_errors.items():
                        st.text(f"{sname}: {serr}")

        st.subheader("相关股票排名")
        st.dataframe(
            df_rank,
            use_container_width=True,
            column_config={
                "相关性": st.column_config.ProgressColumn(
                    min_value=-1, max_value=1, format="%.4f"
                ),
                "综合评分": st.column_config.ProgressColumn(
                    min_value=0, max_value=100, format="%.1f"
                ),
            },
        )

        # Commodity price chart
        st.subheader(f"{commodity_name} 价格走势")
        _show_src("数据来源", comm_src, comm_err)
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=comm_df.index,
                y=comm_df["price"],
                name=commodity_name,
                line=dict(color=cfg["color"], width=2),
            )
        )
        fig.update_layout(
            xaxis_title="日期",
            yaxis_title=f"价格（{cfg['unit']}）",
            height=300,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Save top stock to session state for Analysis tab
        top = df_rank.iloc[0]
        if "selected_stock_code" not in st.session_state:
            st.session_state["selected_stock_code"] = top["股票代码"]
            st.session_state["selected_stock_name"] = top["股票名称"]

        st.info(
            f"💡 综合评分最高：**{top['股票名称']}（{top['股票代码']}）** — "
            f"相关性 {top['相关性']:.4f}，评分 {top['综合评分']}"
        )
    else:
        st.warning("数据不足，无法计算排名。请调整日期范围后重试。")


# ============================================================
# TAB 2 – FACTOR ANALYSIS
# ============================================================

with TAB_ANALYSIS:
    st.header("因子分析")

    stocks_in_cfg = cfg["related_stocks"]
    stock_options = {s["name"]: s["code"] for s in stocks_in_cfg}

    default_name = next(
        (s["name"] for s in stocks_in_cfg
         if s["code"] == st.session_state.get("selected_stock_code")),
        stocks_in_cfg[0]["name"],
    )

    selected_name = st.selectbox(
        "选择股票",
        options=list(stock_options.keys()),
        index=list(stock_options.keys()).index(default_name),
        key="analysis_stock",
    )
    selected_code = stock_options[selected_name]
    st.session_state["selected_stock_code"] = selected_code
    st.session_state["selected_stock_name"] = selected_name

    zscore_window = st.slider("滚动相关性窗口（天）", 20, 120, 60, key="analysis_window")
    with st.expander("ℹ️ 窗口说明（仅影响滚动相关性图表）"):
        st.markdown(
            "此滑块控制**滚动相关性**的回看天数，不影响 Z-Score。"
            "\n\n| 窗口 | 特点 | 适用场景 |"
            "\n|------|------|---------|"
            "\n| 小（20～40 天） | 对近期变化敏感，信号频繁，噪音多 | 短线 |"
            "\n| 中（60 天，默认） | 灵敏度与稳定性平衡，约 3 个月交易日 | 中线 |"
            "\n| 大（90～120 天） | 平滑，误报少，信号滞后 | 中长线 |"
            "\n\n> **Z-Score 使用全量历史数据计算，不受此窗口影响。**"
        )

    with st.spinner("计算因子中…"):
        comm_df, comm_src, comm_err = load_commodity()
        stk_df, stk_src, stk_err = load_stock(selected_code)
        aligned = fac.align(comm_df, stk_df)

    src_col1, src_col2 = st.columns(2)
    with src_col1:
        _show_src("商品数据", comm_src, comm_err)
    with src_col2:
        _show_src("股票数据", stk_src, stk_err)

    if aligned.empty or len(aligned) < zscore_window:
        st.warning("数据不足，请调整日期范围或缩短滚动窗口。")
    else:
        corr_series = fac.rolling_correlation(aligned, window=zscore_window)
        cr_res = fac.cumret_spread_zscore(aligned)
        zs = cr_res["zscore"]
        ll = fac.lead_lag(aligned, max_lag=10)
        current_z = float(zs.dropna().iloc[-1])
        overall_corr = fac.overall_correlation(aligned)
        ann_vol = fac.volatility_annualized(aligned["stock"])

        # --- Metric cards ---
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("全期相关性", f"{overall_corr:.4f}")
        m2.metric("当前 Z-Score", f"{current_z:.2f}",
                  delta="买入信号" if current_z < DEFAULT_STRATEGY["buy_threshold"]
                  else ("卖出信号" if current_z > DEFAULT_STRATEGY["sell_threshold"] else "观望"))
        m3.metric("年化波动率", f"{ann_vol:.1%}")
        m4.metric("最优领先滞后", ll["interpretation"])

        st.divider()

        # --- Chart 1: Dual-axis price chart ---
        st.subheader("价格对比（归一化至100）")
        with st.expander("📐 公式说明"):
            st.latex(r"P^*_t = \frac{P_t}{P_0} \times 100")
            st.markdown(
                "将商品与股票价格统一归一化到同一基准（起始日 = 100），"
                "消除量纲差异后直接比较两者涨跌幅的相对强弱。"
                "\n\n**参数**\n- $P_0$：所选日期范围的第一个交易日收盘价\n- $P_t$：第 $t$ 日收盘价"
            )
        norm_comm = aligned["commodity"] / aligned["commodity"].iloc[0] * 100
        norm_stk = aligned["stock"] / aligned["stock"].iloc[0] * 100

        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(
            x=aligned.index, y=norm_comm,
            name=commodity_name, line=dict(color=cfg["color"], width=2)
        ))
        fig1.add_trace(go.Scatter(
            x=aligned.index, y=norm_stk,
            name=selected_name, line=dict(color="#2CA02C", width=2)
        ))
        fig1.update_layout(
            yaxis_title="归一化价格（基准=100）",
            height=280, margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation="h", y=1.1)
        )
        st.plotly_chart(fig1, use_container_width=True)

        # --- Chart 2: Rolling correlation ---
        st.subheader("滚动相关性")
        with st.expander("📐 公式说明"):
            st.latex(r"\rho_t = \frac{\sum_{i=t-N+1}^{t}(r^C_i - \bar{r}^C)(r^S_i - \bar{r}^S)}{\sqrt{\sum(r^C_i-\bar{r}^C)^2 \cdot \sum(r^S_i-\bar{r}^S)^2}}")
            st.markdown(
                "在每个交易日，取过去 $N$ 天的日对数收益率，计算商品与股票之间的 **Pearson 相关系数**，滚动向前推进。"
                "\n\n**参数**"
                "\n- $r^C_i$：第 $i$ 日商品对数收益率 $= \\ln(P^C_i / P^C_{i-1})$"
                "\n- $r^S_i$：第 $i$ 日股票对数收益率"
                f"\n- $N$：滚动窗口 = **{zscore_window} 天**（可通过上方滑块调整）"
                "\n- 取值范围：$[-1, 1]$，越接近 1 表示同向联动越强"
            )
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=corr_series.index, y=corr_series,
            name="滚动相关性", line=dict(color="#1F77B4", width=1.5),
            fill="tozeroy", fillcolor="rgba(31,119,180,0.1)"
        ))
        fig2.add_hline(y=0, line_dash="dash", line_color="gray")
        fig2.update_layout(
            yaxis=dict(range=[-1, 1]),
            yaxis_title="Pearson 相关系数",
            height=220, margin=dict(l=0, r=0, t=10, b=0)
        )
        st.plotly_chart(fig2, use_container_width=True)

        # --- Chart 3: Z-Score ---
        st.subheader("累积收益 OLS 残差 Z-Score")
        buy_thr = DEFAULT_STRATEGY["buy_threshold"]
        sell_thr = DEFAULT_STRATEGY["sell_threshold"]
        with st.expander("📐 公式说明"):
            st.latex(r"R_t^C = \left(\frac{P_t^C}{P_0^C} - 1\right) \times 100\%")
            st.latex(r"R_t^S = \left(\frac{P_t^S}{P_0^S} - 1\right) \times 100\%")
            st.latex(r"\text{Spread}_t = R_t^C - R_t^S")
            st.latex(r"Z_t = \frac{\text{Spread}_t - \bar{S}}{\sigma_S}")
            st.markdown(
                "**第一步**：将两条价格序列从第1天起各自压缩为累积涨跌幅（%），消除量纲差异\n\n"
                "**第二步**：差值 = 商品累积涨幅% − 股票累积涨幅%，衡量两者的相对强弱\n\n"
                "**第三步**：用**全量历史**的均值 $\\bar{S}$ 和标准差 $\\sigma_S$ 做 Z-Score 标准化\n\n"
                "**关键**：$\\bar{S}$ 和 $\\sigma_S$ 来自整段选定历史，±2 代表真正的历史极端偏离，"
                "不会像滚动窗口那样随时间漂移。\n\n"
                f"- 买入阈值：$Z < {buy_thr}$（股票涨幅相对商品历史性偏低，预期修复）\n"
                f"- 卖出阈值：$Z > {sell_thr}$（股票涨幅相对商品历史性偏高）"
            )

        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=zs.index, y=zs,
            name="Z-Score", line=dict(color="#D62728", width=1.5)
        ))
        fig3.add_hline(y=buy_thr,  line_dash="dot", line_color="green",
                       annotation_text="买入线", annotation_position="left")
        fig3.add_hline(y=sell_thr, line_dash="dot", line_color="red",
                       annotation_text="卖出线", annotation_position="left")
        fig3.add_hline(y=0, line_dash="dash", line_color="gray")
        fig3.update_layout(
            yaxis_title="Z-Score",
            height=220, margin=dict(l=0, r=0, t=10, b=0)
        )
        st.plotly_chart(fig3, use_container_width=True)

        # --- Chart 4: Lead-lag cross-correlation ---
        st.subheader("领先-滞后分析")
        with st.expander("📐 公式说明"):
            st.latex(r"\rho(k) = \text{Corr}(r^C_{t-k},\ r^S_t), \quad k \in [-10, +10]")
            st.markdown(
                "对每个滞后天数 $k$，将商品收益率序列平移 $k$ 天后与股票收益率计算相关系数，"
                "取 $|\\rho(k)|$ 最大的 $k$ 为最优滞后。"
                "\n\n**参数解读**"
                "\n- $k > 0$：商品领先股票 $k$ 天，商品价格变动后股票才跟上"
                "\n- $k < 0$：股票领先商品 $|k|$ 天，市场已将预期提前定价到股票"
                "\n- $k = 0$：同步变动，无明显领先滞后关系"
                "\n- 搜索范围：$k \\in [-10, +10]$ 个交易日"
            )
        lags = list(ll["correlations"].keys())
        corrs = list(ll["correlations"].values())

        colors = ["#2CA02C" if c > 0 else "#D62728" for c in corrs]
        fig4 = go.Figure(go.Bar(
            x=lags, y=corrs, marker_color=colors,
            text=[f"{c:.3f}" for c in corrs], textposition="outside"
        ))
        fig4.add_vline(x=ll["best_lag"], line_dash="dash", line_color="orange",
                       annotation_text=f"最优滞后: {ll['best_lag']} 天")
        fig4.update_layout(
            xaxis_title="滞后天数（正=商品领先，负=股票领先）",
            yaxis_title="相关系数",
            height=260, margin=dict(l=0, r=0, t=10, b=0)
        )
        st.plotly_chart(fig4, use_container_width=True)
        st.caption(f"结论：{ll['interpretation']}，最大相关系数 {ll['best_corr']:.4f}")

        # --- Section: Regression Analysis ---
        st.divider()
        st.subheader("回归分析（日收益率）")
        st.markdown(
            "以**商品日收益率**为 X，**个股日收益率**为 Y，拟合线性回归 **Y = a·X + b**，"
            "用于量化两者在统计学上的线性关系与显著性。"
        )
        with st.expander("📐 公式说明"):
            st.latex(r"Y = a \cdot X + b")
            st.latex(r"a = \frac{\sum(X_i - \bar{X})(Y_i - \bar{Y})}{\sum(X_i - \bar{X})^2}, \quad b = \bar{Y} - a\bar{X}")
            st.markdown(
                "使用 **OLS（普通最小二乘法）** 最小化残差平方和 $\\sum(Y_i - aX_i - b)^2$。"
                "\n\n**输入变量**"
                "\n- $X_i = \\ln(P^C_i / P^C_{i-1})$：商品第 $i$ 日对数收益率"
                "\n- $Y_i = \\ln(P^S_i / P^S_{i-1})$：股票第 $i$ 日对数收益率"
                "\n\n**输出参数**"
                "\n| 参数 | 公式 | 含义 |"
                "\n|------|------|------|"
                "\n| $a$（Coefficient） | 见上 | 商品涨 1% 时股票平均涨幅 |"
                "\n| $b$（Constant） | 见上 | 与商品无关的基础日收益率 |"
                "\n| Std Error | $SE = \\sqrt{\\frac{\\sum e_i^2}{(n-2)\\sum(X_i-\\bar{X})^2}}$ | $a$ 的估计误差，越小越稳定 |"
                "\n| P-value | $t = a/SE$，查 $t$ 分布 | $< 0.05$ 说明 $a$ 统计显著 |"
                "\n| $R^2$ | $1 - SS_{res}/SS_{tot}$ | X 能解释 Y 波动的比例 |"
            )

        reg = fac.regression_analysis(aligned)

        if reg["n_obs"] < 10:
            st.warning("样本量不足，无法进行回归分析。请扩大日期范围。")
        else:
            r1, r2, r3, r4, r5 = st.columns(5)
            r1.metric(
                "Coefficient (a)",
                f"{reg['coefficient']:.4f}",
                help="斜率：商品日收益率每变动1单位，个股日收益率的变动幅度。",
            )
            r2.metric(
                "Constant (b)",
                f"{reg['constant']:.4f}",
                help="截距：与商品收益率无关的个股基础日收益率。",
            )
            r3.metric(
                "Std Error",
                f"{reg['std_err']:.4f}",
                help="斜率估计的标准误，越小说明系数估计越精确。",
            )
            p_val = reg["p_value"]
            r4.metric(
                "P-value",
                f"{p_val:.4f}" if p_val >= 0.0001 else "<0.0001",
                delta="显著" if p_val < 0.05 else "不显著",
                delta_color="normal" if p_val < 0.05 else "off",
                help="H₀: coefficient=0。P<0.05 说明商品收益率对个股收益率有统计显著影响。",
            )
            r5.metric(
                "R-squared",
                f"{reg['r_squared']:.4f}",
                help="拟合优度：商品收益率能解释个股收益率波动的比例。",
            )

            # Scatter plot: X=commodity returns, Y=stock returns, with regression line
            lr_plot = fac.log_returns(aligned).dropna()
            x_vals = lr_plot["commodity"]
            y_vals = lr_plot["stock"]
            x_line = np.linspace(x_vals.min(), x_vals.max(), 200)
            y_line = reg["coefficient"] * x_line + reg["constant"]

            fig_reg = go.Figure()
            fig_reg.add_trace(go.Scatter(
                x=x_vals, y=y_vals,
                mode="markers",
                name="日收益率散点",
                marker=dict(color="rgba(31,119,180,0.35)", size=4),
            ))
            fig_reg.add_trace(go.Scatter(
                x=x_line, y=y_line,
                mode="lines",
                name=f"回归线 (a={reg['coefficient']:.4f}, b={reg['constant']:.4f})",
                line=dict(color="#D62728", width=2),
            ))
            fig_reg.update_layout(
                xaxis_title=f"{commodity_name} 日收益率",
                yaxis_title=f"{selected_name} 日收益率",
                height=340,
                margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig_reg, use_container_width=True)
            st.caption(
                f"样本量：{reg['n_obs']} 个交易日 | "
                f"R²={reg['r_squared']:.4f}，"
                f"{'回归关系在统计上显著（P<0.05）' if p_val < 0.05 else '回归关系在统计上不显著（P≥0.05）'}"
            )


# ============================================================
# TAB 3 – BACKTEST
# ============================================================

with TAB_BACKTEST:
    st.header("策略回测")

    selected_code_bt = st.session_state.get("selected_stock_code", cfg["related_stocks"][0]["code"])
    selected_name_bt = st.session_state.get("selected_stock_name", cfg["related_stocks"][0]["name"])

    st.markdown(f"当前组合：**{commodity_name}** ×  **{selected_name_bt}（{selected_code_bt}）**")

    # Strategy params
    with st.expander("策略参数配置", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            buy_thr = st.number_input("买入 Z-Score 阈值", value=-2.0, step=0.1, key="bt_buy")
            sell_thr = st.number_input("卖出 Z-Score 阈值", value=2.0, step=0.1, key="bt_sell")
        with col2:
            sl = st.number_input("止损比例", value=-0.05, step=0.01,
                                 min_value=-0.5, max_value=0.0, key="bt_sl")
        with col3:
            capital = st.number_input("初始资金（元）", value=100_000, step=10_000, key="bt_cap")

    with st.expander("ℹ️ 参数说明"):
        st.markdown(
            "**策略逻辑**：Z-Score 均值回归 —— 当商品与股票价差偏离历史均值过大时，"
            "预期价差会修复，据此做多股票。"
        )
        st.markdown("**参数详解**")
        st.markdown(
            "| 参数 | 默认值 | 含义 |"
            "\n|------|--------|------|"
            "\n| 买入 Z-Score 阈值 | −2.0 | 当 Z-Score 低于此值时买入：股票相对历史关系偏低，预期向上修复 |"
            "\n| 卖出 Z-Score 阈值 | +2.0 | 当 Z-Score 高于此值时卖出：价差已回归或过度修复 |"
            "\n| 止损比例 | −5% | 持仓期间浮亏超过此比例时强制平仓，控制单笔最大亏损 |"
            "\n| 初始资金 | 10 万元 | 回测起始本金，用于计算资金曲线和收益率 |"
        )
        st.divider()
        st.markdown("**回测指标说明**")
        st.markdown(
            "| 指标 | 公式 | 含义 |"
            "\n|------|------|------|"
            "\n| 总收益率 | $(V_{末} - V_0) / V_0$ | 整个回测期间的累计收益 |"
            "\n| 年化收益率 | $(1 + R)^{1/T} - 1$ | 折算为每年的等效收益率，$T$ 为年数 |"
            "\n| 夏普比率 | $\\bar{r}_d / \\sigma_d \\times \\sqrt{252}$ | 每承担一单位风险获得的超额收益，> 1 为良好 |"
            "\n| 最大回撤 | $\\max(V_{高} - V_{低}) / V_{高}$ | 从历史最高点到最低点的最大跌幅，衡量最坏情况 |"
            "\n| 胜率 | 盈利交易次数 / 总交易次数 | 每笔交易平均获利的概率 |"
        )

    run_bt = st.button("▶ 运行回测", type="primary", key="bt_run")

    if run_bt:
        with st.spinner("回测中…"):
            comm_df, comm_src_bt, comm_err_bt = load_commodity()
            stk_df, stk_src_bt, stk_err_bt = load_stock(selected_code_bt)
            aligned = fac.align(comm_df, stk_df)

            bt_src_col1, bt_src_col2 = st.columns(2)
            with bt_src_col1:
                _show_src("商品数据", comm_src_bt, comm_err_bt)
            with bt_src_col2:
                _show_src("股票数据", stk_src_bt, stk_err_bt)

            if aligned.empty or len(aligned) < 30:
                st.error("数据不足，无法完成回测。请调整日期范围。")
            else:
                cr_res_bt = fac.cumret_spread_zscore(aligned)
                zs = cr_res_bt["zscore"]

                result = bt.run(
                    stock_prices=aligned["stock"],
                    zscore=zs,
                    buy_threshold=buy_thr,
                    sell_threshold=sell_thr,
                    stop_loss=sl,
                    initial_capital=float(capital),
                )
                st.session_state["bt_result"] = result
                st.session_state["bt_aligned"] = aligned

    # Display results (persists until new run)
    if "bt_result" in st.session_state:
        result = st.session_state["bt_result"]
        aligned_bt = st.session_state["bt_aligned"]
        m = result["metrics"]
        portfolio = result["portfolio"]
        trades_df = result["trades"]

        if not m:
            st.warning("回测无有效交易，请调整参数。")
        else:
            # Metric cards
            st.divider()
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("总收益率", f"{m['total_return']:.2%}")
            c2.metric("年化收益率", f"{m['annual_return']:.2%}")
            c3.metric("夏普比率", f"{m['sharpe']:.2f}")
            c4.metric("最大回撤", f"{m['max_drawdown']:.2%}")
            c5.metric("胜率", f"{m['win_rate']:.1%}")

            col_a, col_b = st.columns(2)
            col_a.metric("总交易次数", m["total_trades"])
            col_b.metric("期末资金", f"¥{m['final_value']:,.0f}")

            # Equity curve + drawdown
            st.subheader("资金曲线")
            rolling_max = portfolio["value"].cummax()
            drawdown = (portfolio["value"] - rolling_max) / rolling_max

            fig_eq = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                row_heights=[0.7, 0.3],
                vertical_spacing=0.04,
            )
            fig_eq.add_trace(
                go.Scatter(x=portfolio.index, y=portfolio["value"],
                           name="资金", line=dict(color="#1F77B4", width=2)),
                row=1, col=1,
            )
            # Buy-hold benchmark
            if not aligned_bt.empty:
                bh_start = aligned_bt["stock"].dropna().iloc[0]
                bh = aligned_bt["stock"] / bh_start * float(st.session_state.get("bt_cap", 100_000))
                bh = bh[bh.index.isin(portfolio.index)]
                fig_eq.add_trace(
                    go.Scatter(x=bh.index, y=bh, name="买入持有",
                               line=dict(color="gray", width=1.5, dash="dash")),
                    row=1, col=1,
                )
            fig_eq.add_trace(
                go.Scatter(x=drawdown.index, y=drawdown,
                           name="回撤", fill="tozeroy",
                           line=dict(color="#D62728", width=1),
                           fillcolor="rgba(214,39,40,0.2)"),
                row=2, col=1,
            )
            fig_eq.update_yaxes(title_text="资金（元）", row=1, col=1)
            fig_eq.update_yaxes(title_text="回撤", tickformat=".1%", row=2, col=1)
            fig_eq.update_layout(height=450, margin=dict(l=0, r=0, t=10, b=0),
                                  legend=dict(orientation="h", y=1.05))
            st.plotly_chart(fig_eq, use_container_width=True)

            # Price chart with trade markers
            if not trades_df.empty:
                st.subheader("价格走势（归一化）+ 买卖点")
                buys = trades_df[trades_df["type"] == "买入"]
                sells = trades_df[trades_df["type"].isin(["卖出", "止损卖出", "收盘平仓"])]

                prices = result["aligned_prices"]
                # Normalize stock to 100 for the chart; map buy/sell markers to normalized scale
                norm_base = prices.iloc[0]
                norm_prices = prices / norm_base * 100
                buy_norm = buys["price"] / norm_base * 100 if not buys.empty else buys["price"]
                sell_norm = sells["price"] / norm_base * 100 if not sells.empty else sells["price"]

                # Normalize commodity to 100 on secondary Y-axis
                comm_prices_bt = aligned_bt["commodity"]
                norm_comm_bt = comm_prices_bt / comm_prices_bt.iloc[0] * 100

                fig_trade = make_subplots(specs=[[{"secondary_y": True}]])
                fig_trade.add_trace(go.Scatter(
                    x=norm_prices.index, y=norm_prices,
                    name=selected_name_bt, line=dict(color="#2CA02C", width=1.5)
                ), secondary_y=False)
                fig_trade.add_trace(go.Scatter(
                    x=norm_comm_bt.index, y=norm_comm_bt,
                    name=commodity_name, line=dict(color=cfg["color"], width=1.5, dash="dot"),
                    opacity=0.7
                ), secondary_y=True)
                if not buys.empty:
                    fig_trade.add_trace(go.Scatter(
                        x=buys["date"], y=buy_norm,
                        mode="markers", name="买入",
                        marker=dict(symbol="triangle-up", size=11, color="green")
                    ), secondary_y=False)
                if not sells.empty:
                    fig_trade.add_trace(go.Scatter(
                        x=sells["date"], y=sell_norm,
                        mode="markers", name="卖出",
                        marker=dict(symbol="triangle-down", size=11, color="red")
                    ), secondary_y=False)
                fig_trade.update_yaxes(title_text="股价（归一化=100）", secondary_y=False)
                fig_trade.update_yaxes(title_text=f"{commodity_name}（归一化=100）", secondary_y=True)
                fig_trade.update_layout(
                    height=320, margin=dict(l=0, r=0, t=10, b=0),
                    legend=dict(orientation="h", y=1.1)
                )
                st.plotly_chart(fig_trade, use_container_width=True)

                # Trade log
                st.subheader("交易记录")
                display_trades = trades_df.copy()
                display_trades["date"] = display_trades["date"].astype(str)
                display_trades["return"] = display_trades["return"].map(lambda x: f"{x:.2%}")
                display_trades.columns = ["日期", "类型", "价格", "收益率", "Z-Score", "操作理由"]
                st.dataframe(display_trades, use_container_width=True)

        # Add to watchlist button
        st.divider()
        if st.button("⭐ 加入监控列表", key="bt_add_watch"):
            added = wl.add(
                commodity=commodity_name,
                stock_code=selected_code_bt,
                stock_name=selected_name_bt,
                strategy_params={
                    "buy_threshold": st.session_state.get("bt_buy", -2.0),
                    "sell_threshold": st.session_state.get("bt_sell", 2.0),
                    "stop_loss": st.session_state.get("bt_sl", -0.05),
                },
            )
            if added:
                st.success(f"已将 {selected_name_bt} 加入监控列表！")
            else:
                st.info("该组合已在监控列表中。")


# ============================================================
# TAB 4 – MONITOR
# ============================================================

with TAB_MONITOR:
    st.header("监控列表")

    watchlist = wl.load()

    if not watchlist:
        st.info("监控列表为空。在回测页完成回测后点击「加入监控列表」即可添加。")
    else:
        # Render watchlist table
        display_rows = []
        for item in watchlist:
            display_rows.append(
                {
                    "商品": item["commodity"],
                    "股票": f"{item['stock_name']} ({item['stock_code']})",
                    "策略买入阈值": item["strategy_params"].get("buy_threshold", -2.0),
                    "策略卖出阈值": item["strategy_params"].get("sell_threshold", 2.0),
                    "最近信号": item.get("last_signal") or "—",
                    "最近Z-Score": item.get("last_zscore") or "—",
                    "最近检查": str(item.get("last_checked") or "—")[:19],
                    "添加时间": str(item.get("added_at", ""))[:10],
                }
            )
        st.dataframe(pd.DataFrame(display_rows), use_container_width=True)

        # Refresh signals
        if st.button("🔄 刷新所有信号", key="mon_refresh"):
            signals_found = []
            progress = st.progress(0)
            for i, item in enumerate(watchlist):
                code = item["stock_code"]
                comm_sym = COMMODITY_CONFIG.get(item["commodity"], {}).get("futures_symbol", "AL0")
                params = item.get("strategy_params", DEFAULT_STRATEGY)
                buy_t = float(params.get("buy_threshold", -2.0))
                sell_t = float(params.get("sell_threshold", 2.0))

                try:
                    c_df, _, _ = fetch_commodity(comm_sym, DEFAULT_START, DEFAULT_END)
                    s_df, _, _ = fetch_stock(code, DEFAULT_START, DEFAULT_END)
                    aligned = fac.align(c_df, s_df)
                    if len(aligned) >= 30:
                        cr_res_mon = fac.cumret_spread_zscore(aligned)
                        current_z = float(cr_res_mon["zscore"].dropna().iloc[-1])

                        signal = None
                        if current_z < buy_t:
                            signal = "买入"
                            signals_found.append({
                                "date": str(date.today()),
                                "stock_code": code,
                                "stock_name": item["stock_name"],
                                "commodity": item["commodity"],
                                "signal": signal,
                                "zscore": current_z,
                            })
                        elif current_z > sell_t:
                            signal = "卖出"
                            signals_found.append({
                                "date": str(date.today()),
                                "stock_code": code,
                                "stock_name": item["stock_name"],
                                "commodity": item["commodity"],
                                "signal": signal,
                                "zscore": current_z,
                            })

                        wl.update_signal(item["commodity"], code, signal, current_z)
                except Exception:
                    pass
                progress.progress((i + 1) / len(watchlist))

            st.success(f"刷新完成，发现 {len(signals_found)} 个信号。")
            if signals_found:
                st.subheader("今日信号")
                st.dataframe(pd.DataFrame(signals_found), use_container_width=True)
            st.session_state["latest_signals"] = signals_found
            st.rerun()

        # Remove entries
        st.subheader("移除监控项")
        remove_options = [
            f"{w['stock_name']} ({w['stock_code']}) — {w['commodity']}"
            for w in watchlist
        ]
        to_remove = st.selectbox("选择要移除的项", options=[""] + remove_options, key="mon_remove")
        if st.button("🗑️ 移除", key="mon_do_remove") and to_remove:
            idx = remove_options.index(to_remove)
            item = watchlist[idx]
            wl.remove(item["commodity"], item["stock_code"])
            st.success(f"已移除：{item['stock_name']}")
            st.rerun()

    # ---- Email notification config ----
    st.divider()
    st.subheader("📧 邮件通知配置")
    with st.expander("配置 SMTP 并发送信号邮件"):
        col1, col2 = st.columns(2)
        with col1:
            smtp_host = st.text_input("SMTP 服务器", value="smtp.qq.com", key="smtp_host")
            smtp_port = st.number_input("端口（SSL）", value=465, key="smtp_port")
            sender = st.text_input("发件人邮箱", key="smtp_sender")
            password = st.text_input("授权码 / 密码", type="password", key="smtp_pw")
        with col2:
            recipients_raw = st.text_area("收件人（每行一个）", key="smtp_recipients")
            recipients = [r.strip() for r in recipients_raw.splitlines() if r.strip()]

        signals_to_send = st.session_state.get("latest_signals", [])
        st.caption(f"待发送信号数：{len(signals_to_send)}")

        if st.button("📤 发送邮件", key="smtp_send"):
            if not sender or not password:
                st.error("请填写发件人邮箱和授权码。")
            elif not recipients:
                st.error("请至少填写一个收件人。")
            elif not signals_to_send:
                st.warning("暂无信号可发送，请先刷新信号。")
            else:
                ok, err = notifier.send_signals(
                    smtp_host=smtp_host,
                    smtp_port=int(smtp_port),
                    sender=sender,
                    password=password,
                    recipients=recipients,
                    signals=signals_to_send,
                )
                if ok:
                    st.success("邮件发送成功！")
                else:
                    st.error(f"发送失败：{err}")
