import json
import logging
from typing import Any, Dict, Optional

import redis


logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.client = None
        self.hits = 0
        self.misses = 0
        self._connect()

    def _connect(self) -> None:
        if not self.redis_url:
            return
        try:
            self.client = redis.Redis.from_url(self.redis_url, decode_responses=True)
            self.client.ping()
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self.client = None

    def set_price(self, symbol: str, price: float, ttl: int = 60) -> None:
        if not self.client:
            return
        key = f"price:{symbol.upper()}"
        try:
            self.client.set(key, float(price), ex=ttl)
        except Exception as e:
            logger.error(f"Failed to set price cache for {symbol}: {e}")

    def get_price(self, symbol: str) -> Optional[float]:
        if not self.client:
            return None
        key = f"price:{symbol.upper()}"
        try:
            value = self.client.get(key)
            if value is None:
                self.misses += 1
                return None
            self.hits += 1
            return float(value)
        except Exception as e:
            logger.error(f"Failed to get price cache for {symbol}: {e}")
            return None

    def set_ohlcv(self, symbol: str, interval: str, data: Any, ttl: int = 300) -> None:
        if not self.client:
            return
        key = f"ohlcv:{symbol.upper()}:{interval}"
        try:
            payload = json.dumps(data)
            self.client.set(key, payload, ex=ttl)
        except Exception as e:
            logger.error(f"Failed to set OHLCV cache for {symbol} {interval}: {e}")

    def get_ohlcv(self, symbol: str, interval: str) -> Optional[Any]:
        if not self.client:
            return None
        key = f"ohlcv:{symbol.upper()}:{interval}"
        try:
            value = self.client.get(key)
            if value is None:
                self.misses += 1
                return None
            self.hits += 1
            return json.loads(value)
        except Exception as e:
            logger.error(f"Failed to get OHLCV cache for {symbol} {interval}: {e}")
            return None

    def set_ai_prediction(self, symbol: str, prediction: Dict[str, Any], ttl: int = 300) -> None:
        if not self.client:
            return
        key = f"ai:{symbol.upper()}"
        try:
            payload = json.dumps(prediction)
            self.client.set(key, payload, ex=ttl)
        except Exception as e:
            logger.error(f"Failed to set AI cache for {symbol}: {e}")

    def get_ai_prediction(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        key = f"ai:{symbol.upper()}"
        try:
            value = self.client.get(key)
            if value is None:
                self.misses += 1
                return None
            self.hits += 1
            return json.loads(value)
        except Exception as e:
            logger.error(f"Failed to get AI cache for {symbol}: {e}")
            return None

    def clear_symbol(self, symbol: str) -> None:
        if not self.client:
            return
        prefix = symbol.upper()
        try:
            pattern = f"*{prefix}*"
            for key in self.client.scan_iter(match=pattern):
                self.client.delete(key)
        except Exception as e:
            logger.error(f"Failed to clear cache for {symbol}: {e}")

    def get_stats(self) -> Dict[str, int]:
        return {"hits": self.hits, "misses": self.misses}

