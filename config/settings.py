import os
import argparse
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    BINANCE_WS_URL: str = os.getenv("BINANCE_WS_URL", "wss://stream.binance.com:9443/ws")
    SYMBOLS: List[str] = field(default_factory=lambda: os.getenv("SYMBOLS", "btcusdt,ethusdt,solusdt").split(","))
    ALERT_THRESHOLD_PERCENT: float = float(os.getenv("ALERT_THRESHOLD_PERCENT", os.getenv("ALERT_THRESHOLD", "0.5")))
    SMA_WINDOW_MINUTES: int = int(os.getenv("SMA_WINDOW_MINUTES", os.getenv("SMA_WINDOW", "5")))
    AI_MODE: bool = True
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    ALERT_EMAIL: str = os.getenv("ALERT_EMAIL", "")
    DISCORD_WEBHOOK: str = os.getenv("DISCORD_WEBHOOK_URL", os.getenv("DISCORD_WEBHOOK", ""))
    SLACK_WEBHOOK: str = os.getenv("SLACK_WEBHOOK_URL", os.getenv("SLACK_WEBHOOK", ""))
    MIN_EMAIL_PRIORITY: str = os.getenv("MIN_EMAIL_PRIORITY", "HIGH")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    DEFAULT_AI_MODEL: str = os.getenv("DEFAULT_AI_MODEL", "google/gemini-2.0-flash-001")
    ALERT_COOLDOWN_MINUTES: int = 10
    THROTTLE_PER_SYMBOL_MINUTES: int = 5
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    NGROK_AUTH_TOKEN: str = os.getenv("NGROK_AUTH_TOKEN", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER: str = os.getenv("TWILIO_FROM_NUMBER", "")
    TWILIO_TO_NUMBER: str = os.getenv("TWILIO_TO_NUMBER", "")

    def parse_args(self):
        parser = argparse.ArgumentParser(description="Real-Time Crypto Alert System")
        parser.add_argument("--symbols", type=str, help="Comma-separated crypto symbols (e.g., BTCUSDT,ETHUSDT)")
        parser.add_argument("--threshold", type=float, help="Price change %% for alerts")
        parser.add_argument("--window", type=int, help="Moving average window in minutes")
        parser.add_argument("--ai-mode", type=str, choices=["true", "false"], default="true", help="Enable AI analysis")
        
        args, unknown = parser.parse_known_args()
        
        if args.symbols:
            self.SYMBOLS = [s.strip().lower() for s in args.symbols.split(",")]
        if args.threshold is not None:
            self.ALERT_THRESHOLD_PERCENT = args.threshold
        if args.window is not None:
            self.SMA_WINDOW_MINUTES = args.window
        
        self.AI_MODE = args.ai_mode.lower() == "true"

    @property
    def ALERT_THRESHOLD(self) -> float:
        return self.ALERT_THRESHOLD_PERCENT

    @property
    def SMA_WINDOW(self) -> int:
        return self.SMA_WINDOW_MINUTES

    def validate(self):
        if not self.GEMINI_API_KEY and self.AI_MODE:
            raise ValueError("GEMINI_API_KEY is required in .env file when AI_MODE is enabled")
        if not self.SYMBOLS:
            raise ValueError("SYMBOLS must be provided")
        print(f"Configuration validated. Symbols: {self.SYMBOLS}, Threshold: {self.ALERT_THRESHOLD_PERCENT}%, AI: {self.AI_MODE}")

settings = Settings()
