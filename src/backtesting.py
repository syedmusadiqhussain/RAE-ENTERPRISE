import math
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from src.database import Database


@dataclass
class StrategyConfig:
    symbol: str
    initial_capital: float = 10000.0
    threshold_pct: float = 1.0
    sma_period: int = 20
    stop_loss_pct: float = 5.0
    take_profit_pct: float = 10.0


class BacktestEngine:
    def __init__(self, db: Database, start_date: datetime, end_date: datetime):
        self.db = db
        self.start_date = start_date
        self.end_date = end_date
        self.df: pd.DataFrame = pd.DataFrame()
        self.trades: pd.DataFrame = pd.DataFrame()
        self.equity_curve: pd.Series = pd.Series(dtype=float)
        self.config: StrategyConfig | None = None

    def load_historical_data(self, symbol: str) -> pd.DataFrame:
        if not self.db:
            self.df = pd.DataFrame()
            return self.df
        rows = self.db.get_price_history(symbol, limit=5000)
        if not rows:
            self.df = pd.DataFrame()
            return self.df
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        mask = (df["timestamp"] >= self.start_date) & (df["timestamp"] <= self.end_date)
        df = df.loc[mask].sort_values("timestamp").reset_index(drop=True)
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["close"])
        self.df = df
        return df

    def _generate_signals(self, cfg: StrategyConfig) -> Tuple[pd.DataFrame, pd.DataFrame]:
        df = self.df.copy()
        if df.empty:
            return pd.DataFrame(), pd.Series(dtype=float)
        df["sma"] = df["close"].rolling(cfg.sma_period).mean()
        df["above_sma"] = df["close"] > df["sma"] * (1 + cfg.threshold_pct / 100.0)
        df["below_sma"] = df["close"] < df["sma"]
        position = 0
        entry_price = 0.0
        entry_time = None
        equity = cfg.initial_capital
        equity_curve = []
        cash = cfg.initial_capital
        size = 0.0
        records: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            price = float(row["close"])
            ts = row["timestamp"]
            if position == 0 and row["above_sma"]:
                size = cash / price
                entry_price = price
                entry_time = ts
                cash = 0.0
                position = 1
            elif position == 1:
                take_price = entry_price * (1 + cfg.take_profit_pct / 100.0)
                stop_price = entry_price * (1 - cfg.stop_loss_pct / 100.0)
                exit_signal = row["below_sma"] or price >= take_price or price <= stop_price
                if exit_signal:
                    exit_price = price
                    cash = size * exit_price
                    pnl = cash - cfg.initial_capital
                    ret = pnl / cfg.initial_capital if cfg.initial_capital > 0 else 0.0
                    duration = (ts - entry_time).total_seconds() / 60.0 if entry_time else 0.0
                    records.append(
                        {
                            "entry_time": entry_time,
                            "exit_time": ts,
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "pnl": pnl,
                            "return_pct": ret * 100.0,
                            "duration_min": duration,
                            "symbol": cfg.symbol,
                        }
                    )
                    size = 0.0
                    position = 0
            equity = cash + size * price
            equity_curve.append({"timestamp": ts, "equity": equity})
        equity_df = pd.DataFrame(equity_curve)
        trades_df = pd.DataFrame(records)
        self.trades = trades_df
        self.equity_curve = equity_df.set_index("timestamp")["equity"]
        return trades_df, self.equity_curve

    def simulate_strategy(self, config: Dict[str, Any]) -> Dict[str, Any]:
        cfg = StrategyConfig(**config)
        self.config = cfg
        trades, curve = self._generate_signals(cfg)
        metrics = self.calculate_metrics()
        return {"trades": trades, "equity_curve": curve, "metrics": metrics}

    def calculate_metrics(self) -> Dict[str, Any]:
        if self.equity_curve.empty:
            return {
                "total_return": 0.0,
                "win_rate": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "avg_trade_duration": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
                "trade_count": 0,
            }
        start_equity = float(self.equity_curve.iloc[0])
        end_equity = float(self.equity_curve.iloc[-1])
        total_return = (end_equity / start_equity - 1.0) * 100.0 if start_equity > 0 else 0.0
        ret = 0.0
        win_rate = 0.0
        best_trade = 0.0
        worst_trade = 0.0
        avg_duration = 0.0
        if not self.trades.empty:
            pnl = self.trades["pnl"]
            wins = pnl[pnl > 0]
            ret = pnl.mean() / (start_equity if start_equity > 0 else 1.0)
            win_rate = len(wins) / len(pnl) * 100.0
            best_trade = pnl.max()
            worst_trade = pnl.min()
            avg_duration = float(self.trades["duration_min"].mean())
        eq = self.equity_curve
        returns = eq.pct_change().dropna()
        sharpe_ratio = 0.0
        if not returns.empty and returns.std() > 0:
            sharpe_ratio = float(returns.mean() / returns.std() * math.sqrt(252))
        running_max = eq.cummax()
        drawdown = (eq - running_max) / running_max
        max_drawdown = float(drawdown.min() * 100.0)
        return {
            "total_return": total_return,
            "win_rate": win_rate,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "avg_trade_duration": avg_duration,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "trade_count": int(len(self.trades)),
        }

    def optimize_parameters(self, ranges: Dict[str, List[Any]]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        threshold_vals = ranges.get("threshold_pct") or []
        sma_vals = ranges.get("sma_period") or []
        results = []
        best = None
        best_score = -1e9
        for thr, sma in product(threshold_vals, sma_vals):
            cfg_dict = {
                "symbol": ranges.get("symbol", [None])[0],
                "initial_capital": ranges.get("initial_capital", [10000.0])[0],
                "threshold_pct": thr,
                "sma_period": sma,
                "stop_loss_pct": ranges.get("stop_loss_pct", [5.0])[0],
                "take_profit_pct": ranges.get("take_profit_pct", [10.0])[0],
            }
            self.simulate_strategy(cfg_dict)
            metrics = self.calculate_metrics()
            score = metrics["sharpe_ratio"]
            row = {
                "threshold_pct": thr,
                "sma_period": sma,
                "sharpe_ratio": score,
                "total_return": metrics["total_return"],
            }
            results.append(row)
            if score > best_score:
                best_score = score
                best = {"config": cfg_dict, "metrics": metrics}
        df = pd.DataFrame(results)
        return df, best or {}

    def generate_report(self) -> Dict[str, Any]:
        metrics = self.calculate_metrics()
        trades = self.trades.copy()
        equity = self.equity_curve.reset_index().rename(columns={"index": "timestamp"})
        return {
            "metrics": metrics,
            "trade_log": trades,
            "equity_curve": equity,
        }

