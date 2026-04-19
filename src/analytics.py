from datetime import datetime, timedelta
from typing import Any, Dict, List
from pathlib import Path

import numpy as np
import pandas as pd

from src.database import Database


class Analytics:
    def __init__(self, db: Database):
        self.db = db
        self.root_dir = Path(__file__).resolve().parent.parent

    def _load_alerts_df(self, symbol: str | None = None) -> pd.DataFrame:
        file_path = self.root_dir / "logs" / "alerts.json"
        try:
            df = pd.read_json(file_path)
        except Exception:
            df = pd.DataFrame()
        if df.empty:
            return df
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        if symbol:
            df = df[df["symbol"] == symbol]
        return df

    def get_alert_frequency(self, symbol: str, timeframe: str = "hour") -> pd.DataFrame:
        df = self._load_alerts_df(symbol)
        if df.empty:
            return pd.DataFrame(columns=["period", "count"])
        if timeframe == "day":
            grp = df.groupby(df["datetime"].dt.date).size().reset_index(name="count")
            grp["period"] = grp["datetime"].astype(str)
        else:
            grp = df.groupby(df["datetime"].dt.hour).size().reset_index(name="count")
            grp["period"] = grp["datetime"].astype(str)
        return grp[["period", "count"]]

    def get_accuracy_metrics(self, symbol: str) -> Dict[str, Any]:
        df = self._load_alerts_df(symbol)
        if df.empty:
            return {"accuracy": 0.0, "confusion": [[0, 0], [0, 0]]}
        df = df.sort_values("datetime")
        df["next_return"] = df["current_price"].pct_change().shift(-1)
        df = df.dropna(subset=["next_return"])
        if df.empty:
            return {"accuracy": 0.0, "confusion": [[0, 0], [0, 0]]}
        y_true = df["next_return"] > 0
        preds = []
        for _, row in df.iterrows():
            ai = row.get("ai_analysis") or {}
            action = (ai.get("trade_suggestion") or {}).get("action", "HOLD")
            preds.append(action == "BUY")
        y_pred = np.array(preds)
        if len(y_pred) == 0:
            return {"accuracy": 0.0, "confusion": [[0, 0], [0, 0]]}
        correct = (y_true.values == y_pred).sum()
        acc = correct / len(y_pred) * 100.0
        tp = int(((y_true == True) & (y_pred == True)).sum())
        tn = int(((y_true == False) & (y_pred == False)).sum())
        fp = int(((y_true == False) & (y_pred == True)).sum())
        fn = int(((y_true == True) & (y_pred == False)).sum())
        return {"accuracy": acc, "confusion": [[tp, fp], [fn, tn]]}

    def get_correlation_analysis(self) -> pd.DataFrame:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        frames = []
        for sym in symbols:
            rows = self.db.get_price_history(sym, limit=500)
            df = pd.DataFrame(rows)
            if df.empty:
                continue
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp")
            df[f"{sym}_ret"] = df["close"].pct_change()
            frames.append(df[["timestamp", f"{sym}_ret"]])
        if not frames:
            return pd.DataFrame()
        merged = frames[0]
        for f in frames[1:]:
            merged = merged.merge(f, on="timestamp", how="inner")
        merged = merged.dropna()
        if merged.empty:
            return pd.DataFrame()
        corr = merged[[c for c in merged.columns if c.endswith("_ret")]].corr()
        corr.index = [s.replace("_ret", "") for s in corr.index]
        corr.columns = [s.replace("_ret", "") for s in corr.columns]
        return corr

    def get_volatility_analysis(self, symbol: str) -> pd.DataFrame:
        rows = self.db.get_price_history(symbol, limit=1000)
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp")
        df["ret"] = df["close"].pct_change()
        df["volatility"] = df["ret"].rolling(20).std() * (252 ** 0.5)
        return df[["timestamp", "volatility"]].dropna()

    def get_volume_profile(self, symbol: str) -> pd.DataFrame:
        rows = self.db.get_price_history(symbol, limit=1000)
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame()
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        df = df.dropna(subset=["close", "volume"])
        bins = 20
        df["price_bin"] = pd.cut(df["close"], bins=bins)
        profile = df.groupby("price_bin")["volume"].sum().reset_index()
        profile["price"] = profile["price_bin"].apply(lambda x: x.mid)
        return profile[["price", "volume"]]
