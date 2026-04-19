import datetime

import plotly.express as px
import streamlit as st

from config.settings import settings
from src.database import Database
from src.portfolio import PortfolioAPIKeys, PortfolioTracker


def _get_db() -> Database | None:
    if not settings.DATABASE_URL:
        return None
    return Database(settings.DATABASE_URL)


def show():
    st.header("Portfolio Tracker")
    db = _get_db()
    with st.expander("Binance API Keys", expanded=False):
        api_key = st.text_input("API Key", type="password")
        api_secret = st.text_input("API Secret", type="password")
    if not api_key or not api_secret:
        st.info("Enter Binance read-only API keys to load portfolio.")
        return
    tracker = PortfolioTracker(db, PortfolioAPIKeys(api_key=api_key, api_secret=api_secret))
    balances = tracker.fetch_balances()
    if balances.empty:
        st.warning("No holdings found or failed to fetch balances.")
        return
    total_value = tracker.calculate_portfolio_value(balances)
    pnl = tracker.calculate_pnl(balances)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Value", f"${total_value:,.2f}")
    col2.metric("Today P&L", f"${pnl.get('today', 0.0):,.2f}")
    col3.metric("All-Time P&L", f"${pnl.get('total', 0.0):,.2f}")
    st.subheader("Holdings")
    st.dataframe(balances, use_container_width=True)
    fig_pie = px.pie(balances, values="value", names="symbol", title="Allocation")
    fig_pie.update_layout(template="plotly_dark")
    st.plotly_chart(fig_pie, use_container_width=True)
    st.subheader("Risk Metrics")
    breakdown = tracker.get_position_breakdown(balances)
    st.text(f"Diversification Score: {breakdown['diversification_score']:.2f}")
    st.subheader("Rebalancing Suggestions")
    target = {row["symbol"]: 100.0 / max(len(balances), 1) for _, row in balances.iterrows()}
    recs = tracker.suggest_rebalancing(balances, target)
    if recs:
        st.table(recs)
    else:
        st.info("Portfolio is close to target allocation.")
    st.subheader("Tax Report")
    year = st.number_input("Year", value=datetime.date.today().year, step=1)
    if st.button("Generate Tax CSV"):
        tax_df = tracker.generate_tax_report(int(year))
        if tax_df.empty:
            st.info("No taxable events found for this year.")
        else:
            st.dataframe(tax_df, use_container_width=True)

