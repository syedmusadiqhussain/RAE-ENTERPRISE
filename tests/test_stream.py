import asyncio
from datetime import datetime
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import Settings
from src.stream_engine import EnterpriseStreamEngine


def test_enterprise_stream_engine_triggers_on_spike():
    settings = Settings()
    settings.SYMBOLS = ["btcusdt"]
    settings.AI_MODE = False
    settings.ALERT_THRESHOLD_PERCENT = 5.0

    engine = EnterpriseStreamEngine(settings)
    base_time = int(datetime.now().timestamp() * 1000)

    async def run():
        for i in range(55):
            await engine.process_tick(
                {
                    "symbol": "BTCUSDT",
                    "price": 100.0,
                    "timestamp": base_time + (i * 60_000),
                    "volume": 1.0,
                }
            )
        alert = await engine.process_tick(
            {
                "symbol": "BTCUSDT",
                "price": 106.0,
                "timestamp": base_time + (56 * 60_000),
                "volume": 1.0,
            }
        )
        assert alert is not None
        assert alert["symbol"] == "BTCUSDT"

    asyncio.run(run())
