import os
os.environ.setdefault("PLOTLY_JSON_ENGINE", "json")

import streamlit as st
import json
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots
from datetime import datetime
import time
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import settings
from src.indicators import TechnicalIndicators
from src.data_sources import get_ohlcv_data

if TYPE_CHECKING:
    from src.ai_analyzer import EnterpriseAIAnalyzer

pio.json.config.default_engine = "json"

# --- UTILITIES ---
def safe_float(value):
    """Robustly convert string with symbols, ranges or text to float."""
    if value is None: return 0.0
    if isinstance(value, (int, float)): return float(value)
    
    try:
        # 1. Try direct conversion
        return float(value)
    except (ValueError, TypeError):
        try:
            # 2. Extract first number (handles "$84.65", "Price: 100", "84.65 - 84.85")
            match = re.search(r"[-+]?\d*\.?\d+", str(value).replace(',', ''))
            if match:
                return float(match.group())
        except:
            pass
    return 0.0

st.set_page_config(
    page_title="RAE Enterprise",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS FOR THEME ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: white; }
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #3e4251; }
    [data-testid="stSidebar"] { background-color: #161b22; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def get_ai_client() -> "EnterpriseAIAnalyzer":
    from src.ai_analyzer import EnterpriseAIAnalyzer
    return EnterpriseAIAnalyzer(settings)


def load_ohlcv(symbol, interval):
    try:
        df = get_ohlcv_data(symbol, interval, limit=200)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    try:
        ti = TechnicalIndicators()
        df = ti.add_all_indicators(df)
        df = ti.add_emas_to_df(df)
    except Exception:
        pass
    return df

def load_alerts():
    file_path = ROOT_DIR / "logs" / "alerts.json"
    if not file_path.exists():
        return pd.DataFrame()
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if not data: return pd.DataFrame()
            df = pd.DataFrame(data)
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
    except: return pd.DataFrame()

def draw_enterprise_chart(df, symbol):
    if df.empty:
        return None

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
        subplot_titles=(f"{symbol} Price", "Volume"),
    )

    fig.add_trace(
        go.Candlestick(
            x=df["timestamp"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Price",
        ),
        row=1,
        col=1,
    )

    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()

    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["ema_50"],
            name="EMA 50",
            line=dict(color="orange", width=2),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["ema_200"],
            name="EMA 200",
            line=dict(color="purple", width=2),
        ),
        row=1,
        col=1,
    )

    colors = ["green" if row["close"] > row["open"] else "red" for _, row in df.iterrows()]

    fig.add_trace(
        go.Bar(
            x=df["timestamp"],
            y=df["volume"],
            marker_color=colors,
            name="Volume",
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        height=800,
        template="plotly_dark",
        showlegend=True,
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        dragmode="pan",
    )

    config = {
        "modeBarButtonsToAdd": [
            "drawline",
            "drawopenpath",
            "drawclosedpath",
            "drawcircle",
            "drawrect",
            "eraseshape",
        ],
        "scrollZoom": True,
        "displaylogo": False,
    }

    return fig, config


def draw_candlestick(symbol_data):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, subplot_titles=(f'{symbol_data["symbol"]} Real-Time', 'Volume'), 
                        row_width=[0.2, 0.7])

    fig.add_trace(go.Candlestick(
        x=[datetime.now()],
        open=[symbol_data['current_price'] * 0.999],
        high=[symbol_data['current_price'] * 1.001],
        low=[symbol_data['current_price'] * 0.998],
        close=[symbol_data['current_price']],
        name="Price"
    ), row=1, col=1)

    inds = symbol_data['indicators']
    fig.add_trace(go.Scatter(x=[datetime.now()], y=[inds['ema_50']], name="EMA 50", line=dict(color='orange')), row=1, col=1)
    fig.add_trace(go.Scatter(x=[datetime.now()], y=[inds['ema_200']], name="EMA 200", line=dict(color='blue')), row=1, col=1)

    fig.update_layout(height=600, template="plotly_dark", showlegend=True,
                      xaxis_rangeslider_visible=False)
    return fig
    if 'RSI_14' in df.columns:
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['RSI_14'], name="RSI", line=dict(color='purple')), row=3, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)

    # 6. MACD
    if 'MACD_12_26_9' in df.columns:
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['MACD_12_26_9'], name="MACD", line=dict(color='cyan')), row=4, col=1)
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['MACDs_12_26_9'], name="Signal", line=dict(color='magenta')), row=4, col=1)
        fig.add_trace(go.Bar(x=df['timestamp'], y=df['MACDh_12_26_9'], name="Hist"), row=4, col=1)

    # Layout Customization
    fig.update_layout(
        height=900,
        template="plotly_dark",
        showlegend=True,
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
        dragmode='pan', # Default to pan for better UX
    )
    
    # Enable drawing tools & interactive features
    config = {
        'modeBarButtonsToAdd': [
            'drawline',
            'drawopenpath',
            'drawclosedpath',
            'drawcircle',
            'drawrect',
            'eraseshape'
        ],
        'scrollZoom': True,
        'displaylogo': False,
    }
    
    return fig, config

st.sidebar.title("RAE ENTERPRISE")
page = st.sidebar.radio(
    "Navigation",
    [
        "📊 Live Trading",
        "🔙 Backtesting",
        "💼 Portfolio",
        "📈 Analytics",
        "⚙️ Settings",
    ],
)


def show_settings_page():
    st.header("Settings")
    st.subheader("API Keys")
    st.text_input("OpenRouter API Key", type="password")
    st.text_input("Gemini API Key", type="password")
    st.subheader("Alert Thresholds")
    st.slider("Alert Threshold %", min_value=0.5, max_value=10.0, value=float(settings.ALERT_THRESHOLD_PERCENT), step=0.5)
    st.subheader("Notifications")
    st.checkbox("Email Alerts", value=bool(settings.ALERT_EMAIL))
    st.checkbox("Slack Alerts", value=bool(settings.SLACK_WEBHOOK))
    st.checkbox("Telegram Alerts", value=bool(settings.TELEGRAM_BOT_TOKEN))
    st.subheader("Database")
    if st.button("Test Database Connection"):
        ok = bool(settings.DATABASE_URL)
        if ok:
            st.success("Database configuration present.")
        else:
            st.error("DATABASE_URL is not set.")
    st.subheader("Cache")
    st.write("Redis URL:", settings.REDIS_URL)
    if st.button("Clear Cache (manual)"):
        st.info("Clear cache triggered (implement Redis flush in future).")
    st.subheader("Config Export/Import")
    st.text_area("Config JSON", value="{}", height=120)

st.sidebar.divider()
theme = st.sidebar.toggle("Dark Mode", True)
enable_sound = st.sidebar.toggle("Sound Notifications", True)

# --- SOUND LOGIC ---
if enable_sound and 'last_alert_count' in st.session_state:
    current_count = len(load_alerts())
    if current_count > st.session_state.last_alert_count:
        st.components.v1.html(
            """
            <audio autoplay>
                <source src="https://www.soundjay.com/buttons/beep-01a.mp3" type="audio/mpeg">
            </audio>
            """,
            height=0,
        )
    st.session_state.last_alert_count = current_count
else:
    st.session_state.last_alert_count = len(load_alerts())

if page == "📊 Live Trading":
    symbol_options = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    selected_symbol = st.sidebar.selectbox("Symbol", symbol_options, index=0)
    timeframe = st.sidebar.radio("Timeframe", ["1m", "5m", "15m", "1h", "4h", "1d"], index=1, horizontal=True)

    st.sidebar.divider()
    st.sidebar.subheader("Chart Templates")
    if "chart_templates" not in st.session_state:
        st.session_state.chart_templates = {}
    template_name = st.sidebar.text_input("Template Name", value="Default")
    if st.sidebar.button("Save Current View"):
        st.session_state.chart_templates[template_name] = {
            "symbol": selected_symbol,
            "timeframe": timeframe,
        }
        st.sidebar.success(f"Saved {template_name}!")
    if st.session_state.chart_templates:
        load_template = st.sidebar.selectbox("Load Template", list(st.session_state.chart_templates.keys()))
        if st.sidebar.button("Apply Template"):
            t = st.session_state.chart_templates[load_template]
            st.sidebar.info(f"Applying {load_template}...")

    st.title("RAE ENTERPRISE")
    df = load_alerts()
    if not df.empty:
        latest = df.iloc[-1]
        st.subheader("Market Performance")
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("Total Alerts", len(df))
        m_col2.metric("Critical Alerts", len(df[df["priority"] == "CRITICAL"]))
        m_col3.metric("Avg Volatility", f"{df['price_change_pct'].mean():.2f}%")
        m_col4.metric("Last Update", latest["datetime"].strftime("%H:%M:%S"))
        st.divider()
        cols = st.columns(4)
        cols[0].metric("LATEST PRICE", f"${latest['current_price']:,.2f}", f"{latest['price_change_pct']:.2f}%")
        cols[1].metric("PRIORITY", latest["priority"])
        ai = latest.get("ai_analysis", {})
        sentiment_color = "green" if ai.get("sentiment_label") == "Bullish" else "red"
        cols[2].markdown(
            f"**SENTIMENT**  \n<h2 style='color:{sentiment_color}'>{ai.get('sentiment_score', 50)}/100</h2>",
            unsafe_allow_html=True,
        )
        cols[3].metric("CATEGORY", latest.get("category", "VOLATILITY"))
    st.divider()
    col_left, col_right = st.columns([2, 1])
    with col_left:
        ohlcv_df = load_ohlcv(selected_symbol, timeframe)
        if not ohlcv_df.empty:
            last_row = ohlcv_df.iloc[-1]
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Open", f"${last_row['open']:.2f}")
            col2.metric("High", f"${last_row['high']:.2f}")
            col3.metric("Low", f"${last_row['low']:.2f}")
            col4.metric("Close", f"${last_row['close']:.2f}")
            chart_key = f"chart_{selected_symbol}_{timeframe}"
            fig, config = draw_enterprise_chart(ohlcv_df, selected_symbol)
            st.plotly_chart(fig, use_container_width=True, key=chart_key, config=config)
        else:
            st.info(f"Waiting for {selected_symbol} market data connection...")
    with col_right:
        st.subheader("AI Trading Signal")
        if not settings.GEMINI_API_KEY or not settings.OPENROUTER_API_KEY:
            st.info("Set GEMINI_API_KEY and OPENROUTER_API_KEY in .env to enable AI ensemble.")
        elif ohlcv_df.empty:
            st.write("Waiting for market data to run AI analysis.")
        else:
            last_price = float(ohlcv_df["close"].iloc[-1])
            client = get_ai_client()
            try:
                result = client.analyze_market(selected_symbol, last_price, ohlcv_df)
            except Exception:
                st.warning("AI ensemble temporarily unavailable.")
            else:
                models = result.get("models", {})
                consensus = result.get("consensus", {})

                def action_color(a):
                    a = str(a).upper()
                    if a == "BUY":
                        return "lime"
                    if a == "SELL":
                        return "red"
                    return "gold"

                with st.expander("Multi-Model Predictions", expanded=True):
                    order = [("Gemini", "gemini"), ("Llama", "llama"), ("Qwen", "qwen")]
                    for label, key in order:
                        data = models.get(key)
                        if not data:
                            continue
                        action = str(data.get("action", "HOLD")).upper()
                        confidence = float(data.get("confidence", 0))
                        color = action_color(action)
                        st.markdown(
                            f"<span style='color:{color}'>🤖 {label}: {action} ({confidence:.0f}%)</span>",
                            unsafe_allow_html=True,
                        )
                    if consensus:
                        cons_action = str(consensus.get("action", "HOLD")).upper()
                        cons_conf = float(consensus.get("confidence", 0))
                        cons_color = action_color(cons_action)
                        st.markdown("━━━━━━━━━━━━━━━━━━━━━━")
                        st.markdown(
                            f"<span style='color:{cons_color}'>✅ CONSENSUS: {cons_action} ({cons_conf:.0f}%)</span>",
                            unsafe_allow_html=True,
                        )
    st.subheader("Enterprise Alert Feed")
    if not df.empty:
        display_df = df[
            [
                "datetime",
                "symbol",
                "priority",
                "category",
                "current_price",
                "price_change_pct",
                "conditional_rule",
            ]
        ].iloc[::-1]
        st.dataframe(display_df, use_container_width=True)
        if st.button("Export CSV"):
            out_path = ROOT_DIR / "logs" / "export.csv"
            df.to_csv(out_path)
            st.success("Exported to logs/export.csv")
elif page == "🔙 Backtesting":
    import src.backtest_dashboard as backtest_dashboard

    backtest_dashboard.show()
elif page == "💼 Portfolio":
    import src.portfolio_dashboard as portfolio_dashboard

    portfolio_dashboard.show()
elif page == "📈 Analytics":
    import src.analytics_dashboard as analytics_dashboard

    analytics_dashboard.show()
elif page == "⚙️ Settings":
    show_settings_page()
