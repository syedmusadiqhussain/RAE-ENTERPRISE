from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

try:
    from binance.client import Client as BinanceClient
except ImportError:
    BinanceClient = None

from src.database import Database


@dataclass
class PortfolioAPIKeys:
    api_key: str
    api_secret: str


class PortfolioTracker:
    def __init__(self, db: Optional[Database], api_keys: PortfolioAPIKeys):
        self.db = db
        self.api_keys = api_keys
        if BinanceClient is None:
            self.client = None
        else:
            self.client = BinanceClient(api_key=api_keys.api_key, api_secret=api_keys.api_secret)

    def fetch_balances(self) -> pd.DataFrame:
        if not self.client:
            return pd.DataFrame(columns=["symbol", "amount", "price", "value"])
        account = self.client.get_account()
        balances = account.get("balances", [])
        rows = []
        tickers = {t["symbol"]: float(t["price"]) for t in self.client.get_all_tickers()}
        for b in balances:
            free = float(b["free"])
            locked = float(b["locked"])
            amount = free + locked
            if amount <= 0:
                continue
            asset = b["asset"]
            symbol = asset + "USDT"
            price = tickers.get(symbol, 0.0)
            value = amount * price
            rows.append({"symbol": symbol, "amount": amount, "price": price, "value": value})
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        total = df["value"].sum()
        df["allocation_pct"] = df["value"] / total * 100.0
        return df

    def calculate_portfolio_value(self, df: pd.DataFrame) -> float:
        if df.empty:
            return 0.0
        return float(df["value"].sum())

    def calculate_pnl(self, df: pd.DataFrame) -> Dict[str, float]:
        return {"realized": 0.0, "unrealized": 0.0, "total": 0.0}

    def get_position_breakdown(self, df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty:
            return {"diversification_score": 0.0, "allocation": []}
        alloc = df[["symbol", "allocation_pct"]].to_dict(orient="records")
        score = float(100.0 / max(len(df), 1))
        return {"diversification_score": score, "allocation": alloc}

    def suggest_rebalancing(self, df: pd.DataFrame, target_alloc: Dict[str, float]) -> List[Dict[str, Any]]:
        if df.empty:
            return []
        recs = []
        for _, row in df.iterrows():
            symbol = row["symbol"]
            current = float(row["allocation_pct"])
            target = float(target_alloc.get(symbol, current))
            delta = target - current
            if abs(delta) < 1.0:
                continue
            direction = "buy" if delta > 0 else "sell"
            recs.append({"symbol": symbol, "delta_pct": delta, "action": direction})
        return recs

    def generate_tax_report(self, year: int) -> pd.DataFrame:
        if not self.db:
            return pd.DataFrame(columns=["date", "symbol", "side", "quantity", "price", "proceeds", "cost_basis"])
        alerts = self.db.get_alert_history("BTCUSDT", f"{year}-01-01", f"{year}-12-31")  # placeholder
        df = pd.DataFrame(alerts)
        if df.empty:
            return pd.DataFrame(columns=["date", "symbol", "side", "quantity", "price", "proceeds", "cost_basis"])
        df_out = pd.DataFrame(
            {
                "date": pd.to_datetime(df["timestamp"]),
                "symbol": df["symbol"],
                "side": ["sell"] * len(df),
                "quantity": 0.0,
                "price": df["current_price"],
                "proceeds": 0.0,
                "cost_basis": 0.0,
            }
        )
        return df_out

