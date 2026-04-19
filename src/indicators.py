"""Technical indicator utilities used by the real-time stream engine and dashboard."""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional, List

try:
    from ta.momentum import RSIIndicator, StochasticOscillator
    from ta.trend import EMAIndicator, MACD
    from ta.volatility import BollingerBands, AverageTrueRange
    from ta.volume import VolumeWeightedAveragePrice
except Exception:
    RSIIndicator = None
    StochasticOscillator = None
    EMAIndicator = None
    MACD = None
    BollingerBands = None
    AverageTrueRange = None
    VolumeWeightedAveragePrice = None

logger = logging.getLogger(__name__)

def calculate_enterprise_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 50:
        return df
    if any(x is None for x in (RSIIndicator, EMAIndicator, MACD, BollingerBands, AverageTrueRange, VolumeWeightedAveragePrice)):
        return df

    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce")

    df["RSI_14"] = RSIIndicator(close=close, window=14).rsi()
    df["RSI_7"] = RSIIndicator(close=close, window=7).rsi()

    macd = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
    df["MACD_12_26_9"] = macd.macd()
    df["MACDs_12_26_9"] = macd.macd_signal()
    df["MACDh_12_26_9"] = macd.macd_diff()

    bb = BollingerBands(close=close, window=20, window_dev=2)
    df["BBL_20_2.0"] = bb.bollinger_lband()
    df["BBM_20_2.0"] = bb.bollinger_mavg()
    df["BBU_20_2.0"] = bb.bollinger_hband()

    df["EMA_9"] = EMAIndicator(close=close, window=9).ema_indicator()
    df["EMA_21"] = EMAIndicator(close=close, window=21).ema_indicator()
    df["EMA_50"] = EMAIndicator(close=close, window=50).ema_indicator()
    df["EMA_200"] = EMAIndicator(close=close, window=200).ema_indicator()

    try:
        vwap = VolumeWeightedAveragePrice(high=high, low=low, close=close, volume=volume, window=14)
        df["VWAP"] = vwap.volume_weighted_average_price()
    except Exception:
        df["VWAP"] = np.nan

    if StochasticOscillator is not None:
        so = StochasticOscillator(high=high, low=low, close=close, window=14, smooth_window=3)
        df["STOCHk_14_3_3"] = so.stoch()
        df["STOCHd_14_3_3"] = so.stoch_signal()

    atr = AverageTrueRange(high=high, low=low, close=close, window=14)
    df["ATR_14"] = atr.average_true_range()

    df["vol_sma_20"] = df["volume"].rolling(20).mean()
    df["relative_volume"] = df["volume"] / df["vol_sma_20"]

    return df

def calculate_support_resistance(df: pd.DataFrame, window: int = 20) -> Dict[str, float]:
    if df.empty:
        return {"support": 0.0, "resistance": 0.0}
    size = min(len(df), window)
    recent = df.tail(size)
    support = float(recent["low"].min())
    resistance = float(recent["high"].max())
    return {"support": support, "resistance": resistance}

def detect_patterns(df: pd.DataFrame) -> List[str]:
    patterns: List[str] = []
    if len(df) < 2:
        return patterns

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    if prev["close"] < prev["open"] and curr["close"] > curr["open"]:
        prev_body = abs(prev["close"] - prev["open"])
        curr_body = abs(curr["close"] - curr["open"])
        if curr_body > prev_body:
            patterns.append("Bullish Engulfing")

    if len(df) >= 5:
        recent = df.tail(5)
        highs = recent["high"].values
        h0, h1, h2, h3, h4 = highs
        if h2 > h1 and h2 > h3 and h1 > h0 and h3 > h4:
            patterns.append("Head & Shoulders")

    vol = df["volume"].iloc[-1]
    vol_mean = df["volume"].rolling(20).mean().iloc[-1] if len(df) >= 20 else df["volume"].mean()
    if vol_mean and vol > vol_mean * 2:
        patterns.append("Volume Surge")

    return patterns


class TechnicalIndicators:
    def calculate_sma(self, df: pd.DataFrame, period: int) -> pd.DataFrame:
        df[f"SMA_{period}"] = df["close"].rolling(period).mean()
        return df

    def calculate_ema(self, df: pd.DataFrame, period: int) -> pd.DataFrame:
        ema = df["close"].ewm(span=period, adjust=False).mean()
        df[f"ema_{period}"] = ema
        df[f"EMA_{period}"] = ema
        return df

    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        if RSIIndicator is None:
            return df
        close = pd.to_numeric(df["close"], errors="coerce")
        df[f"RSI_{period}"] = RSIIndicator(close=close, window=period).rsi()
        return df

    def calculate_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        if MACD is None:
            return df
        close = pd.to_numeric(df["close"], errors="coerce")
        m = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
        df["MACD_12_26_9"] = m.macd()
        df["MACDs_12_26_9"] = m.macd_signal()
        df["MACDh_12_26_9"] = m.macd_diff()
        return df

    def calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        if BollingerBands is None:
            return df
        close = pd.to_numeric(df["close"], errors="coerce")
        bb = BollingerBands(close=close, window=period, window_dev=2)
        df["BBL_20_2.0"] = bb.bollinger_lband()
        df["BBM_20_2.0"] = bb.bollinger_mavg()
        df["BBU_20_2.0"] = bb.bollinger_hband()
        return df

    def calculate_support_resistance(self, df: pd.DataFrame, window: int = 20) -> Dict[str, float]:
        return calculate_support_resistance(df, window)

    def detect_patterns(self, df: pd.DataFrame) -> List[str]:
        return detect_patterns(df)

    def add_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        return calculate_enterprise_indicators(df)

    def add_emas_to_df(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.calculate_ema(df, 50)
        df = self.calculate_ema(df, 200)
        return df
