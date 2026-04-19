import os
import logging
import pandas as pd
from typing import Optional, Dict
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from src.indicators import calculate_enterprise_indicators, calculate_support_resistance, detect_patterns

logger = logging.getLogger(__name__)

class EnterpriseStreamEngine:
    """
    Enterprise-grade stream processing engine with smart alerts,
    advanced indicators, and multi-symbol state management.
    """
    def __init__(self, settings, db=None, cache=None):
        self.settings = settings
        self.db = db
        self.cache = cache
        self.root_dir = Path(__file__).resolve().parent.parent
        self.buffers = {}
        self.last_alerts = {}
        self.symbol_states = {}
        self.tick_count = 0

    def is_within_time_rules(self) -> bool:
        """Check if current time is within 9AM-5PM and not a weekend."""
        now = datetime.now()
        # Weekday: 0=Monday, 6=Sunday
        if now.weekday() >= 5: # Weekend
            return False
        if not (9 <= now.hour < 17): # 9AM-5PM
            return False
        return True

    def categorize_alert(self, df: pd.DataFrame, levels: dict) -> str:
        """Categorize the alert based on price and indicator behavior."""
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        if latest["close"] > levels.get("resistance", 0) or latest["close"] > latest.get("BBU_20_2.0", 0):
            return "BREAKOUT"
        
        # 2. Reversal: RSI overbought/oversold with price pivot
        if (latest.get('RSI_14', 50) > 70 or latest.get('RSI_14', 50) < 30):
            return "REVERSAL"
            
        avg_vol = df["volume"].rolling(20).mean().iloc[-1]
        if latest["volume"] > avg_vol * 2:
            return "VOLUME_SURGE"
            
        return "VOLATILITY"

    def check_conditional_rules(self, symbol: str, current_change: float) -> Optional[str]:
        """
        Check for cross-symbol conditional rules.
        Example: "Alert ETH if BTC > 3%"
        """
        self.symbol_states[symbol] = current_change
        
        if symbol == 'ETHUSDT' and self.symbol_states.get('BTCUSDT', 0) > 3.0:
            return "BTC_CORRELATION_BREAKOUT"
            
        return None

    def calculate_alert_priority(self, change_pct: float) -> str:
        abs_change = abs(change_pct)
        if abs_change > 5.0:
            return "CRITICAL"
        if abs_change > 2.0:
            return "HIGH"
        if abs_change > 1.0:
            return "MEDIUM"
        return "LOW"

    def get_priority(self, change_pct: float) -> str:
        return self.calculate_alert_priority(change_pct)

    def get_throttle_limit(self, priority: str) -> int:
        """
        Mobile Optimization: Return throttle minutes based on priority.
        Higher priority alerts bypass longer cooldowns.
        """
        if priority == "CRITICAL": return 1 # 1 min for critical
        if priority == "HIGH": return 5     # 5 mins for high
        if priority == "MEDIUM": return 15   # 15 mins for medium
        return 30                            # 30 mins for low (save mobile data)

    def _save_ohlcv_buffer(self, symbol: str):
        """Saves the current buffer to a JSON file for the dashboard."""
        try:
            buffer_data = list(self.buffers[symbol])
            # Convert timestamps to string for JSON serialization
            serializable_data = []
            for b in buffer_data:
                item = b.copy()
                item['timestamp'] = b['timestamp'].isoformat()
                serializable_data.append(item)

            import json
            out_dir = self.root_dir / "logs" / "ohlcv"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{symbol.lower()}.json"
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(serializable_data, f)
        except Exception as e:
            logger.error(f"Error saving OHLCV buffer for {symbol}: {e}")

    async def process_tick(self, tick: dict):
        self.tick_count += 1
        symbol = tick['symbol']
        price = tick['price']
        timestamp = tick['timestamp']
        
        # 0. Time Rules Check
        if not self.is_within_time_rules():
            # In a real system, we might still process for indicators but skip alerts
            pass 

        # 1. Throttling & Cooldown (Pre-priority check)
        # We need a rough priority estimate for early throttling
        # In a real system we'd calculate indicators first, but for mobile data saving
        # we can do a quick price-based check.
        # However, to be accurate, we'll continue to step 2/3 and throttle at the end.
        
        # 2. Buffer Management (OHLCV creation)
        if symbol not in self.buffers:
            self.buffers[symbol] = deque(maxlen=500)
        bar = {
            'timestamp': pd.to_datetime(timestamp, unit='ms'),
            'open': price * (1 - 0.0001),
            'high': price * (1 + 0.0005),
            'low': price * (1 - 0.0005),
            'close': price,
            'volume': tick.get('volume', 100.0)
        }
        self.buffers[symbol].append(bar)
        if self.cache is not None:
            self.cache.set_price(symbol, price)
        if self.db is not None:
            self.db.save_price_tick(symbol, bar)

        # Save historical buffer for dashboard visualization
        self._save_ohlcv_buffer(symbol)

        if len(self.buffers[symbol]) < 50:
            return None

        # 3. Indicator Calculation
        df = pd.DataFrame(list(self.buffers[symbol]))
        df = calculate_enterprise_indicators(df)
        levels = calculate_support_resistance(df)
        pattern_list = detect_patterns(df)
        
        latest = df.iloc[-1]
        prev_close = df.iloc[-2]['close']
        price_change_pct = abs((price - prev_close) / prev_close) * 100
        priority = self.get_priority(price_change_pct)

        # 4. Smart Alert Logic
        # Mobile-First Throttling
        now = datetime.now()
        throttle_mins = self.get_throttle_limit(priority)
        if symbol in self.last_alerts:
            if now < self.last_alerts[symbol] + timedelta(minutes=throttle_mins):
                return None

        if price_change_pct >= self.settings.ALERT_THRESHOLD_PERCENT:
            self.last_alerts[symbol] = now # Update last alert time
            
            category = self.categorize_alert(df, levels)
            conditional_rule = self.check_conditional_rules(symbol, price_change_pct)
            
            alert_payload = {
                "symbol": symbol,
                "current_price": float(price),
                "price_change_pct": float(price_change_pct),
                "priority": self.get_priority(price_change_pct),
                "category": category,
                "conditional_rule": conditional_rule,
                "indicators": {
                    "rsi": float(latest.get("RSI_14", 0)),
                    "macd": float(latest.get("MACD_12_26_9", 0)),
                    "bb_upper": float(latest.get("BBU_20_2.0", 0)),
                    "bb_lower": float(latest.get("BBL_20_2.0", 0)),
                    "ema_50": float(latest.get("EMA_50", 0)),
                    "ema_200": float(latest.get("EMA_200", 0)),
                    "vwap": float(latest.get("VWAP", 0)),
                    "relative_volume": float(latest.get("relative_volume", 1.0))
                },
                "levels": {
                    "support": float(levels.get("support", 0.0)),
                    "resistance": float(levels.get("resistance", 0.0))
                },
                "patterns": pattern_list,
                "timestamp": timestamp
            }
            
            return alert_payload

        return None
