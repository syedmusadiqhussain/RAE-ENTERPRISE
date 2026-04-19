import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from config.settings import settings
from src.analytics import Analytics
from src.database import Database


def _get_db() -> Database | None:
    if not settings.DATABASE_URL:
        return None
    return Database(settings.DATABASE_URL)


def show():
    st.header("Analytics")
    db = _get_db()
    if not db:
        st.warning("DATABASE_URL is not configured. Analytics requires database access.")
        return
    analytics = Analytics(db)
    symbol = st.selectbox("Symbol", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    freq_df = analytics.get_alert_frequency(symbol, timeframe="hour")
    if not freq_df.empty:
        fig_freq = px.bar(freq_df, x="period", y="count", title="Alert Frequency by Hour")
        fig_freq.update_layout(template="plotly_dark")
        st.plotly_chart(fig_freq, use_container_width=True)
    acc = analytics.get_accuracy_metrics(symbol)
    st.subheader("AI Accuracy")
    st.metric("Accuracy", f"{acc['accuracy']:.2f}%")
    corr_df = analytics.get_correlation_analysis()
    if not corr_df.empty:
        fig_corr = px.imshow(corr_df.values, x=corr_df.columns, y=corr_df.index, color_continuous_scale="Viridis")
        fig_corr.update_layout(title="Correlation Matrix", template="plotly_dark")
        st.plotly_chart(fig_corr, use_container_width=True)
    vol_df = analytics.get_volatility_analysis(symbol)
    if not vol_df.empty:
        fig_vol = px.line(vol_df, x="timestamp", y="volatility", title="Historical Volatility")
        fig_vol.update_layout(template="plotly_dark")
        st.plotly_chart(fig_vol, use_container_width=True)
    vp = analytics.get_volume_profile(symbol)
    if not vp.empty:
        fig_vp = px.bar(vp, x="price", y="volume", title="Volume Profile by Price")
        fig_vp.update_layout(template="plotly_dark")
        st.plotly_chart(fig_vp, use_container_width=True)
    st.subheader("False Positive / Negative Analysis")
    conf = acc["confusion"]
    st.write(f"TP: {conf[0][0]}, FP: {conf[0][1]}, FN: {conf[1][0]}, TN: {conf[1][1]}")

