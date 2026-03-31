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
        start_input = st.date_input("开始", value=date(2023, 1, 1), key="date_start")
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
def _commodity(symbol: str, s: str, e: str) -> pd.DataFrame:
    return fetch_commodity(symbol, s, e)


@st.cache_data(show_spinner=False)
def _stock(code: str, s: str, e: str) -> pd.DataFrame:
    return fetch_stock(code, s, e)


def load_commodity() -> pd.DataFrame:
    return _commodity(cfg["futures_symbol"], start_str, end_str)


def load_stock(code: str) -> pd.DataFrame:
    return _stock(code, start_str, end_str)


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
        comm_df = load_commodity()

        rows = []
        for stock_info in cfg["related_stocks"]:
            code = stock_info["code"]
            name = stock_info["name"]
            industry = stock_info["industry"]

            stk_df = load_stock(code)
            aligned = fac.align(comm_df, stk_df)

            if aligned.empty or len(aligned) < 30:
                continue

            corr = fac.overall_correlation(aligned)
            vol = fac.volatility_annualized(aligned["stock"])
            sp = fac.spread(aligned)
            zs = fac.rolling_zscore(sp, window=min(60, len(sp) // 2))
            current_z = float(zs.dropna().iloc[-1]) if not zs.dropna().empty else 0.0

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
                }
            )

    if rows:
        df_rank = pd.DataFrame(rows).sort_values("综合评分", ascending=False).reset_index(drop=True)
        df_rank.index += 1

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

    zscore_window = st.slider("Z-Score 滚动窗口（天）", 20, 120, 60, key="analysis_window")

    with st.spinner("计算因子中…"):
        comm_df = load_commodity()
        stk_df = load_stock(selected_code)
        aligned = fac.align(comm_df, stk_df)

    if aligned.empty or len(aligned) < zscore_window:
        st.warning("数据不足，请调整日期范围或缩短滚动窗口。")
    else:
        corr_series = fac.rolling_correlation(aligned, window=zscore_window)
        sp = fac.spread(aligned)
        zs = fac.rolling_zscore(sp, window=zscore_window)
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
        st.subheader("价差 Z-Score")
        buy_thr = DEFAULT_STRATEGY["buy_threshold"]
        sell_thr = DEFAULT_STRATEGY["sell_threshold"]

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
            zw = st.slider("Z-Score 窗口（天）", 20, 120, 60, key="bt_zw")
            sl = st.number_input("止损比例", value=-0.05, step=0.01,
                                 min_value=-0.5, max_value=0.0, key="bt_sl")
        with col3:
            capital = st.number_input("初始资金（元）", value=100_000, step=10_000, key="bt_cap")

    run_bt = st.button("▶ 运行回测", type="primary", key="bt_run")

    if run_bt:
        with st.spinner("回测中…"):
            comm_df = load_commodity()
            stk_df = load_stock(selected_code_bt)
            aligned = fac.align(comm_df, stk_df)

            if aligned.empty or len(aligned) < zw:
                st.error("数据不足，无法完成回测。请调整日期范围或缩短窗口。")
            else:
                sp = fac.spread(aligned)
                zs = fac.rolling_zscore(sp, window=zw)

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
                st.subheader("股价走势 + 买卖点")
                buys = trades_df[trades_df["type"] == "买入"]
                sells = trades_df[trades_df["type"].isin(["卖出", "止损卖出", "收盘平仓"])]

                prices = result["aligned_prices"]
                fig_trade = go.Figure()
                fig_trade.add_trace(go.Scatter(
                    x=prices.index, y=prices,
                    name=selected_name_bt,
                    line=dict(color="#2CA02C", width=1.5)
                ))
                if not buys.empty:
                    fig_trade.add_trace(go.Scatter(
                        x=buys["date"], y=buys["price"],
                        mode="markers", name="买入",
                        marker=dict(symbol="triangle-up", size=10, color="green")
                    ))
                if not sells.empty:
                    fig_trade.add_trace(go.Scatter(
                        x=sells["date"], y=sells["price"],
                        mode="markers", name="卖出",
                        marker=dict(symbol="triangle-down", size=10, color="red")
                    ))
                fig_trade.update_layout(
                    yaxis_title="股价（元）",
                    height=300, margin=dict(l=0, r=0, t=10, b=0),
                    legend=dict(orientation="h", y=1.1)
                )
                st.plotly_chart(fig_trade, use_container_width=True)

                # Trade log
                st.subheader("交易记录")
                display_trades = trades_df.copy()
                display_trades["date"] = display_trades["date"].astype(str)
                display_trades["return"] = display_trades["return"].map(lambda x: f"{x:.2%}")
                display_trades.columns = ["日期", "类型", "价格", "收益率", "Z-Score"]
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
                    "zscore_window": st.session_state.get("bt_zw", 60),
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
                zw = int(params.get("zscore_window", 60))
                buy_t = float(params.get("buy_threshold", -2.0))
                sell_t = float(params.get("sell_threshold", 2.0))

                try:
                    c_df = fetch_commodity(comm_sym, DEFAULT_START, DEFAULT_END)
                    s_df = fetch_stock(code, DEFAULT_START, DEFAULT_END)
                    aligned = fac.align(c_df, s_df)
                    if len(aligned) >= zw:
                        sp = fac.spread(aligned)
                        zs = fac.rolling_zscore(sp, window=zw)
                        current_z = float(zs.dropna().iloc[-1])

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
