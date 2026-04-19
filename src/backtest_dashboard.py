import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config.settings import settings
from src.backtesting import BacktestEngine
from src.database import Database


def _get_db() -> Database | None:
    if not settings.DATABASE_URL:
        return None
    return Database(settings.DATABASE_URL)


def show():
    st.header("Backtesting Engine")
    db = _get_db()
    if not db:
        st.warning("DATABASE_URL is not configured. Backtesting requires historical data in PostgreSQL.")
        return
    today = datetime.date.today()
    start, end = st.date_input(
        "Backtest Date Range",
        value=(today - datetime.timedelta(days=30), today),
    )
    symbol = st.selectbox("Symbol", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    col1, col2, col3 = st.columns(3)
    threshold_pct = col1.number_input("Threshold %", value=1.0, step=0.1)
    sma_period = col2.number_input("SMA Period", value=20, min_value=5, max_value=200, step=1)
    initial_capital = col3.number_input("Initial Capital", value=10000.0, step=1000.0)
    col4, col5 = st.columns(2)
    stop_loss_pct = col4.number_input("Stop Loss %", value=5.0, step=0.5)
    take_profit_pct = col5.number_input("Take Profit %", value=10.0, step=0.5)
    if st.button("Run Backtest"):
        engine = BacktestEngine(
            db=db,
            start_date=datetime.datetime.combine(start, datetime.time.min),
            end_date=datetime.datetime.combine(end, datetime.time.max),
        )
        df = engine.load_historical_data(symbol)
        if df.empty:
            st.warning("No historical data found for this range.")
            return
        result = engine.simulate_strategy(
            {
                "symbol": symbol,
                "initial_capital": initial_capital,
                "threshold_pct": threshold_pct,
                "sma_period": int(sma_period),
                "stop_loss_pct": stop_loss_pct,
                "take_profit_pct": take_profit_pct,
            }
        )
        report = engine.generate_report()
        metrics = report["metrics"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Return", f"{metrics['total_return']:.2f}%")
        m2.metric("Win Rate", f"{metrics['win_rate']:.2f}%")
        m3.metric("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}")
        m4.metric("Max Drawdown", f"{metrics['max_drawdown']:.2f}%")
        equity_df = report["equity_curve"]
        fig_eq = px.line(equity_df, x="timestamp", y="equity", title="Equity Curve")
        fig_eq.update_layout(template="plotly_dark")
        st.plotly_chart(fig_eq, use_container_width=True)
        trades = report["trade_log"]
        if not trades.empty:
            fig_hist = px.histogram(trades, x="return_pct", nbins=30, title="Trade Return Distribution")
            fig_hist.update_layout(template="plotly_dark")
            st.plotly_chart(fig_hist, use_container_width=True)
            trades["month"] = trades["exit_time"].dt.to_period("M").astype(str)
            monthly = trades.groupby("month")["pnl"].sum().reset_index()
            if not monthly.empty:
                fig_month = px.imshow(
                    monthly[["pnl"]].T.values,
                    labels={"x": "Month", "y": "", "color": "P&L"},
                    x=monthly["month"],
                )
                fig_month.update_layout(title="Monthly P&L Heatmap", template="plotly_dark")
                st.plotly_chart(fig_month, use_container_width=True)
            st.subheader("Trade Log")
            st.dataframe(trades, use_container_width=True)
        else:
            st.info("No trades generated for this configuration.")
    st.divider()
    st.subheader("Parameter Optimization")
    oc1, oc2, oc3, oc4 = st.columns(4)
    thr_min = oc1.number_input("Min Threshold %", value=0.5, step=0.5)
    thr_max = oc2.number_input("Max Threshold %", value=3.0, step=0.5)
    thr_step = oc3.number_input("Threshold Step", value=0.5, step=0.5)
    sma_min = oc4.number_input("Min SMA", value=10, step=5)
    sma_max = st.number_input("Max SMA", value=50, step=5)
    sma_step = st.number_input("SMA Step", value=10, step=5)
    if st.button("Run Optimization"):
        engine = BacktestEngine(
            db=db,
            start_date=datetime.datetime.combine(start, datetime.time.min),
            end_date=datetime.datetime.combine(end, datetime.time.max),
        )
        df = engine.load_historical_data(symbol)
        if df.empty:
            st.warning("No historical data found for this range.")
            return
        thr_vals = list(np.arange(thr_min, thr_max + 1e-9, thr_step))
        sma_vals = list(range(int(sma_min), int(sma_max) + 1, int(sma_step)))
        grid, best = engine.optimize_parameters(
            {
                "symbol": [symbol],
                "initial_capital": [initial_capital],
                "threshold_pct": thr_vals,
                "sma_period": sma_vals,
                "stop_loss_pct": [stop_loss_pct],
                "take_profit_pct": [take_profit_pct],
            }
        )
        if grid.empty:
            st.info("No results from optimization.")
            return
        pivot = grid.pivot(index="sma_period", columns="threshold_pct", values="sharpe_ratio")
        fig_hm = px.imshow(
            pivot.values,
            labels={"x": "Threshold %", "y": "SMA Period", "color": "Sharpe"},
            x=pivot.columns,
            y=pivot.index,
        )
        fig_hm.update_layout(title="Sharpe Ratio Heatmap", template="plotly_dark")
        st.plotly_chart(fig_hm, use_container_width=True)
        if best:
            st.success(
                f"Best Sharpe {best['metrics']['sharpe_ratio']:.2f} with threshold "
                f"{best['config']['threshold_pct']}% and SMA {best['config']['sma_period']}"
            )

