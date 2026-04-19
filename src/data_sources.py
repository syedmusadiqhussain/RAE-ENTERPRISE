import asyncio
import json
import logging
import time
import aiohttp
from typing import AsyncGenerator, List, Dict
from functools import lru_cache

try:
    from binance.client import Client as BinanceClient
except ImportError:
    BinanceClient = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BinanceWebSocket:
    def __init__(self, symbols: List[str], base_url: str = "wss://stream.binance.com:9443/ws"):
        self.symbols = [s.lower() for s in symbols]
        self.base_url = base_url
        self.running = True

    def _build_combined_stream_url(self) -> str:
        streams = "/".join([f"{s}@trade" for s in self.symbols])
        base = (self.base_url or "").strip()
        if not base:
            base = "wss://stream.binance.com:9443/ws"
        if base.endswith("/ws"):
            base = base[: -len("/ws")]
        base = base.rstrip("/")
        return f"{base}/stream?streams={streams}"

    async def stream(self) -> AsyncGenerator[dict, None]:
        """
        Connects to Binance WebSocket and yields price ticks.
        """
        url = self._build_combined_stream_url()
        
        retry_delay = 1
        max_retry_delay = 60

        while self.running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(url) as ws:
                        logger.info(f"Connected to Binance WebSocket for {self.symbols}")
                        retry_delay = 1 # Reset retry delay on success
                        
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                if "data" in data:
                                    tick = data["data"]
                                    # Convert to standard format
                                    yield {
                                        "symbol": tick["s"],
                                        "price": float(tick["p"]),
                                        "timestamp": int(tick["E"]),
                                        "volume": float(tick["q"])
                                    }
                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                logger.warning("WebSocket closed")
                                break
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.error("WebSocket error")
                                break
            except Exception as e:
                logger.error(f"WebSocket connection failed: {e}")
                
            if self.running:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)

    def stop(self):
        self.running = False


_OHLCV_LIMIT = 500

def _interval_to_binance(interval: str) -> str:
    interval = interval.lower()
    mapping = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }
    if interval not in mapping:
        raise ValueError(f"Unsupported interval: {interval}")
    return mapping[interval]


@lru_cache(maxsize=32)
def get_ohlcv_data(symbol: str, interval: str = "5m", limit: int = 100, cache=None):
    import pandas as pd

    if BinanceClient is None:
        raise RuntimeError("python-binance is not installed. Please install 'python-binance'.")

    if cache is not None:
        cached = cache.get_ohlcv(symbol, interval)
        if cached:
            frame = pd.DataFrame(cached)
            if not frame.empty:
                return frame
    client = BinanceClient()
    binance_interval = _interval_to_binance(interval)
    max_limit = _OHLCV_LIMIT
    use_limit = max(1, min(int(limit), max_limit))
    try:
        klines = client.get_klines(symbol=symbol.upper(), interval=binance_interval, limit=use_limit)
    except Exception as e:
        logger.error(f"Failed to fetch OHLCV for {symbol} @ {interval}: {e}")
        raise

    if not klines:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    frame = pd.DataFrame(
        klines,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
            "ignore",
        ],
    )
    frame["timestamp"] = pd.to_datetime(frame["open_time"], unit="ms")
    frame["open"] = frame["open"].astype(float)
    frame["high"] = frame["high"].astype(float)
    frame["low"] = frame["low"].astype(float)
    frame["close"] = frame["close"].astype(float)
    frame["volume"] = frame["volume"].astype(float)
    result = frame[["timestamp", "open", "high", "low", "close", "volume"]]
    if cache is not None:
        cache.set_ohlcv(symbol, interval, result.to_dict(orient="records"))
    return result
