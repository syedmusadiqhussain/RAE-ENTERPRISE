import logging
from collections import deque
from datetime import datetime, timedelta
import random
import pandas as pd

logger = logging.getLogger(__name__)


class MockStreamEngine:
    def __init__(self, settings):
        self.settings = settings
        self.threshold = settings.ALERT_THRESHOLD_PERCENT
        self.window_size = settings.SMA_WINDOW_MINUTES * 60
        self.buffers = {}
        self.tick_count = 0

    async def process_tick(self, tick: dict):
        self.tick_count += 1
        if self.tick_count % 50 == 0:
            logger.info(f"Processed {self.tick_count} ticks. Current {tick['symbol']} price: ${tick['price']:.2f}")

        symbol = tick["symbol"]
        price = tick["price"]

        if symbol not in self.buffers:
            self.buffers[symbol] = deque(maxlen=200)

        self.buffers[symbol].append(price)

        prices = list(self.buffers[symbol])
        if len(prices) < 10:
            return None

        sma = sum(prices) / len(prices)

        import math

        mean = sma
        variance = sum((x - mean) ** 2 for x in prices) / len(prices)
        volatility = math.sqrt(variance)

        price_change_pct = abs((price - sma) / sma) * 100

        if price_change_pct > self.threshold:
            return {
                "symbol": symbol,
                "current_price": price,
                "sma": sma,
                "volatility": volatility,
                "last_timestamp": tick["timestamp"],
            }

        return None


class MockDataEngine:
    def __init__(self, seed: int = 42):
        self.random = random.Random(seed)

    def generate_mock_tick(self, symbol: str, base_price: float) -> dict:
        drift = base_price * 0.0005
        noise = self.random.gauss(0, base_price * 0.0008)
        price = max(0.0, base_price + drift + noise)
        qty = abs(self.random.gauss(1.0, 0.3))
        ts = int(datetime.utcnow().timestamp() * 1000)
        return {
            "symbol": symbol.upper(),
            "price": price,
            "quantity": qty,
            "timestamp": ts,
        }

    def generate_mock_ohlcv(self, symbol: str, periods: int = 100, base_price: float = 100.0) -> pd.DataFrame:
        rows = []
        price = base_price
        now = datetime.utcnow()
        for i in range(periods):
            step = self.random.gauss(0, price * 0.003)
            open_price = price
            close_price = max(0.0, price + step)
            high = max(open_price, close_price) + abs(self.random.gauss(0, price * 0.0015))
            low = min(open_price, close_price) - abs(self.random.gauss(0, price * 0.0015))
            vol = abs(self.random.gauss(100, 25))
            ts = now - timedelta(minutes=periods - i)
            rows.append(
                {
                    "symbol": symbol.upper(),
                    "timestamp": ts,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close_price,
                    "volume": vol,
                }
            )
            price = close_price
        df = pd.DataFrame(rows)
        return df

    def simulate_price_movement(self, symbol: str, base_price: float, steps: int = 50) -> list:
        prices = []
        price = base_price
        for _ in range(steps):
            step = self.random.gauss(0, base_price * 0.002)
            price = max(0.0, price + step)
            prices.append(price)
        return prices

    def get_test_alerts(self) -> list:
        now = int(datetime.utcnow().timestamp() * 1000)
        return [
            {
                "symbol": "BTCUSDT",
                "current_price": 68000.0,
                "price_change_pct": 2.5,
                "priority": "HIGH",
                "category": "BREAKOUT",
                "timestamp": now,
            },
            {
                "symbol": "ETHUSDT",
                "current_price": 2000.0,
                "price_change_pct": -1.2,
                "priority": "MEDIUM",
                "category": "REVERSAL",
                "timestamp": now,
            },
        ]
