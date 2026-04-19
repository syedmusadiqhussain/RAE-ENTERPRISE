import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras


logger = logging.getLogger(__name__)


class Database:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.conn = None
        self._connect()

    def _connect(self) -> None:
        if not self.connection_string:
            return
        try:
            self.conn = psycopg2.connect(self.connection_string)
            self.conn.autocommit = True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            self.conn = None

    def create_tables(self) -> None:
        if not self.conn:
            return
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        schema_path = os.path.join(base_dir, "database", "schema.sql")
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                sql = f.read()
            with self.conn.cursor() as cur:
                cur.execute(sql)
        except Exception as e:
            logger.error(f"Failed to execute schema.sql: {e}")

    def save_alert(self, alert_data: Dict[str, Any]) -> None:
        if not self.conn:
            return
        try:
            ts_ms = alert_data.get("timestamp")
            if isinstance(ts_ms, (int, float)):
                ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            else:
                ts = datetime.now(tz=timezone.utc)
            symbol = alert_data.get("symbol")
            indicators = alert_data.get("indicators") or {}
            levels = alert_data.get("levels") or {}
            ai = alert_data.get("ai_analysis") or {}
            trade = ai.get("trade_suggestion") or {}
            ensemble = ai.get("ensemble") or {}
            models = {
                "gemini": ensemble.get("models", {}).get("gemini") if isinstance(ensemble.get("models"), dict) else None,
                "llama": ensemble.get("models", {}).get("llama") if isinstance(ensemble.get("models"), dict) else None,
                "qwen": ensemble.get("models", {}).get("qwen") if isinstance(ensemble.get("models"), dict) else None,
            }
            ai_action = trade.get("action")
            ai_conf = ai.get("sentiment_score")
            gemini_action = None
            llama_action = None
            qwen_action = None
            if isinstance(models.get("gemini"), dict):
                gemini_action = models["gemini"].get("action")
            if isinstance(models.get("llama"), dict):
                llama_action = models["llama"].get("action")
            if isinstance(models.get("qwen"), dict):
                qwen_action = models["qwen"].get("action")
            patterns = alert_data.get("patterns") or ai.get("patterns_confirmed") or []
            reasoning = ai.get("reasoning") or ""
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO alerts (
                        timestamp,
                        symbol,
                        exchange,
                        price,
                        change_percent,
                        volume,
                        sma_5m,
                        ema_50,
                        ema_200,
                        rsi,
                        macd,
                        bollinger_upper,
                        bollinger_lower,
                        support,
                        resistance,
                        ai_action,
                        ai_confidence,
                        gemini_action,
                        llama_action,
                        qwen_action,
                        priority,
                        category,
                        patterns,
                        reasoning
                    )
                    VALUES (
                        %(timestamp)s,
                        %(symbol)s,
                        %(exchange)s,
                        %(price)s,
                        %(change_percent)s,
                        %(volume)s,
                        %(sma_5m)s,
                        %(ema_50)s,
                        %(ema_200)s,
                        %(rsi)s,
                        %(macd)s,
                        %(bollinger_upper)s,
                        %(bollinger_lower)s,
                        %(support)s,
                        %(resistance)s,
                        %(ai_action)s,
                        %(ai_confidence)s,
                        %(gemini_action)s,
                        %(llama_action)s,
                        %(qwen_action)s,
                        %(priority)s,
                        %(category)s,
                        %(patterns)s,
                        %(reasoning)s
                    )
                    """,
                    {
                        "timestamp": ts,
                        "symbol": symbol,
                        "exchange": alert_data.get("exchange", "binance"),
                        "price": alert_data.get("current_price"),
                        "change_percent": alert_data.get("price_change_pct"),
                        "volume": alert_data.get("indicators", {}).get("relative_volume"),
                        "sma_5m": None,
                        "ema_50": indicators.get("ema_50"),
                        "ema_200": indicators.get("ema_200"),
                        "rsi": indicators.get("rsi"),
                        "macd": indicators.get("macd"),
                        "bollinger_upper": indicators.get("bb_upper"),
                        "bollinger_lower": indicators.get("bb_lower"),
                        "support": levels.get("support"),
                        "resistance": levels.get("resistance"),
                        "ai_action": ai_action,
                        "ai_confidence": ai_conf,
                        "gemini_action": gemini_action,
                        "llama_action": llama_action,
                        "qwen_action": qwen_action,
                        "priority": alert_data.get("priority"),
                        "category": alert_data.get("category"),
                        "patterns": patterns,
                        "reasoning": reasoning,
                    },
                )
        except Exception as e:
            logger.error(f"Failed to save alert to database: {e}")

    def get_latest_alerts(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.conn:
            return []
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM alerts
                    WHERE symbol = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """,
                    (symbol, limit),
                )
                rows = cur.fetchall()
                return list(rows)
        except Exception as e:
            logger.error(f"Failed to fetch latest alerts: {e}")
            return []

    def get_alert_history(self, symbol: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        if not self.conn:
            return []
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM alerts
                    WHERE symbol = %s
                      AND timestamp BETWEEN %s AND %s
                    ORDER BY timestamp ASC
                    """,
                    (symbol, start_date, end_date),
                )
                rows = cur.fetchall()
                return list(rows)
        except Exception as e:
            logger.error(f"Failed to fetch alert history: {e}")
            return []

    def save_price_tick(self, symbol: str, ohlc_data: Dict[str, Any]) -> None:
        if not self.conn:
            return
        try:
            ts = ohlc_data.get("timestamp")
            if isinstance(ts, datetime):
                ts_db = ts
            else:
                ts_db = datetime.now(tz=timezone.utc)
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO price_history (timestamp, symbol, open, high, low, close, volume)
                    VALUES (%(timestamp)s, %(symbol)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s)
                    ON CONFLICT (symbol, timestamp) DO UPDATE
                    SET open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume
                    """,
                    {
                        "timestamp": ts_db,
                        "symbol": symbol,
                        "open": ohlc_data.get("open"),
                        "high": ohlc_data.get("high"),
                        "low": ohlc_data.get("low"),
                        "close": ohlc_data.get("close"),
                        "volume": ohlc_data.get("volume"),
                    },
                )
        except Exception as e:
            logger.error(f"Failed to save price history: {e}")

    def get_price_history(self, symbol: str, limit: int = 500) -> List[Dict[str, Any]]:
        if not self.conn:
            return []
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM price_history
                    WHERE symbol = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """,
                    (symbol, limit),
                )
                rows = cur.fetchall()
                return list(rows)
        except Exception as e:
            logger.error(f"Failed to fetch price history: {e}")
            return []

    def close(self) -> None:
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

