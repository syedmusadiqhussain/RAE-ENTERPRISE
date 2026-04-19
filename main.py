import asyncio
import logging
import signal
import sys
import os
import json
from fastapi import FastAPI
import uvicorn
import socket
from threading import Thread
from pathlib import Path
from config.settings import settings
from src.data_sources import BinanceWebSocket
from src.alerts import AlertManager
from src.stream_engine import EnterpriseStreamEngine
from src.database import Database
from src.cache import RedisCache
from fastapi.middleware.cors import CORSMiddleware

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# FastAPI Instance
app = FastAPI(title="RAE Mobile Backend")
latest_alerts_buffer = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/alerts")
async def get_alerts():
    """Returns the latest buffered alerts for mobile consumption."""
    return latest_alerts_buffer[-20:] # Return last 20 alerts
 
@app.get("/health")
async def health():
    return {"status": "ok"}

# Setup logging
_ROOT_DIR = Path(__file__).resolve().parent
(_ROOT_DIR / "logs").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(_ROOT_DIR / "logs" / "app.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CryptoAlertSystem:
    def __init__(self):
        self.settings = settings
        self.ws = BinanceWebSocket(settings.SYMBOLS, base_url=settings.BINANCE_WS_URL)
        self.ai = None
        self.alerts = AlertManager(settings)
        self.db = Database(self.settings.DATABASE_URL) if self.settings.DATABASE_URL else None
        if self.db is not None:
            self.db.create_tables()
        self.cache = RedisCache(self.settings.REDIS_URL) if self.settings.REDIS_URL else None
        self.engine = EnterpriseStreamEngine(settings, db=self.db, cache=self.cache)
        self.stop_event = asyncio.Event()

    async def handle_alert(self, alert_data):
        """
        Handles detected alerts: AI analysis + Broadcasting.
        """
        logger.info(f"🚨 {alert_data['priority']} Alert detected for {alert_data['symbol']}!")
        ai_analysis = {}
        if self.settings.AI_MODE and self.ai is not None:
            try:
                ai_analysis = await self.ai.analyze_alert(alert_data)
            except Exception as e:
                logger.error(f"AI analysis failed for {alert_data['symbol']}: {e}")
        
        # Broadcast alert
        alert_payload = {**alert_data, 'ai_analysis': ai_analysis}
        
        # Update FastAPI buffer
        latest_alerts_buffer.append(alert_payload)
        if len(latest_alerts_buffer) > 100:
            latest_alerts_buffer.pop(0)
            
        await self.alerts.broadcast(alert_payload)
        if self.db is not None:
            self.db.save_alert(alert_payload)

    async def start(self):
        """
        Starts the system: WebSocket and Processing loop.
        """
        self.settings.parse_args()
        self.settings.validate()

        if self.settings.AI_MODE:
            from src.ai_analyzer import EnterpriseAIAnalyzer

            self.ai = EnterpriseAIAnalyzer(self.settings)
        else:
            self.ai = None
        
        # Start FastAPI in a separate thread
        api_port = int(os.getenv("API_PORT", "8000"))
        dashboard_port = int(os.getenv("DASHBOARD_PORT", "8501"))
        def run_api():
            try:
                uvicorn.run(app, host="0.0.0.0", port=api_port, log_level="error")
            except OSError:
                fallback_port = api_port + 1
                uvicorn.run(app, host="0.0.0.0", port=fallback_port, log_level="error")
        
        api_thread = Thread(target=run_api, daemon=True)
        api_thread.start()
        logger.info(f"📡 FastAPI Mobile Backend live at http://0.0.0.0:{api_port}")
        
        # Compute LAN IP for mobile access hints
        def get_lan_ip():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                return ip
            except:
                return "localhost"
        lan_ip = get_lan_ip()
        logger.info(f"📱 Mobile URLs: Dashboard http://{lan_ip}:{dashboard_port} | API http://{lan_ip}:{api_port}/api/alerts")
        
        self.ws = BinanceWebSocket(self.settings.SYMBOLS, base_url=self.settings.BINANCE_WS_URL)
        self.engine = EnterpriseStreamEngine(self.settings, db=self.db, cache=self.cache)
        
        logger.info("🚀 RAE: Enterprise Trading Platform Engine Starting...")
        
        try:
            async for tick in self.ws.stream():
                if self.stop_event.is_set():
                    break
                
                # Process tick through the enterprise engine
                alert_data = await self.engine.process_tick(tick)
                
                if alert_data:
                    # Run alert handling as a background task
                    asyncio.create_task(self.handle_alert(alert_data))
                    
        except Exception as e:
            logger.error(f"Main loop error: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self):
        logger.info("Shutting down engine...")
        self.stop_event.set()
        self.ws.stop()
        if self.db is not None:
            self.db.close()

if __name__ == "__main__":
    system = CryptoAlertSystem()
    
    try:
        asyncio.run(system.start())
    except KeyboardInterrupt:
        logger.info("Engine stopped by user.")
