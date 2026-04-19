"""Alert broadcasting utilities (console, email, webhooks, messaging)."""

import logging
import smtplib
import requests
import json
import os
import re
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# --- UTILITIES ---
def safe_float(value):
    """Robustly convert string with symbols, ranges or text to float."""
    if value is None: return 0.0
    if isinstance(value, (int, float)): return float(value)
    
    try:
        # 1. Try direct conversion
        return float(value)
    except (ValueError, TypeError):
        try:
            # 2. Extract first number (handles "$84.65", "Price: 100", "84.65 - 84.85")
            match = re.search(r"[-+]?\d*\.?\d+", str(value).replace(',', ''))
            if match:
                return float(match.group())
        except:
            pass
    return 0.0

logger = logging.getLogger(__name__)

class AlertManager:
    def __init__(self, settings):
        self.settings = settings
        self.root_dir = Path(__file__).resolve().parent.parent
        self.logs_dir = self.root_dir / "logs"

    def send_console(self, data: dict):
        """Prints alert to console in enterprise format."""
        timestamp = datetime.fromtimestamp(data['timestamp'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n🚨 {data['priority']} ALERT - {timestamp} UTC")
        print("━" * 40)
        print(f"Symbol:      {data['symbol']}")
        print(f"Price:       ${data['current_price']:.2f}")
        print(f"Change:      {data['price_change_pct']:.2f}%")
        print(f"Category:    {data.get('category', 'VOLATILITY')}")
        
        if 'ai_analysis' in data and data['ai_analysis']:
            ai = data['ai_analysis']
            print("\n🤖 AI ANALYSIS")
            print("━" * 40)
            print(f"Sentiment:   {ai.get('sentiment_label')} ({ai.get('sentiment_score')}/100)")
            print(f"Action:      {ai.get('trade_suggestion', {}).get('action')}")
            
            # Safely cast to float for CLI display
            sl = safe_float(ai.get('trade_suggestion', {}).get('stop_loss', 0))
            tp = safe_float(ai.get('trade_suggestion', {}).get('take_profit', 0))
            p1h = safe_float(ai.get('predictions', {}).get('1h', 0))
            p24h = safe_float(ai.get('predictions', {}).get('24h', 0))

            print(f"SL/TP:       SL: ${sl:.2f} | TP: ${tp:.2f}")
            print(f"Patterns:    {', '.join(ai.get('patterns_confirmed', ['None']))}")
            print(f"Predictions: 1h: ${p1h:.2f} | 24h: ${p24h:.2f}")
            print(f"News Sent.:  {ai.get('news_sentiment_score', 0)}")
            print(f"Reasoning:   {ai.get('reasoning')}")
        else:
            print("\n🤖 AI ANALYSIS")
            print("━" * 40)
            print("AI analysis unavailable at the moment.")
        print("━" * 40 + "\n")

    def send_email(self, data: dict):
        if not self.settings.SMTP_USERNAME or not self.settings.ALERT_EMAIL:
            return

        # Priority filtering for emails
        priority_scores = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        min_priority = self.settings.MIN_EMAIL_PRIORITY.upper()
        current_priority = data.get('priority', 'LOW').upper()

        if priority_scores.get(current_priority, 0) < priority_scores.get(min_priority, 3):
            logger.info(f"ℹ️ Skipping email alert for {data['symbol']} (Priority: {current_priority}). Email threshold is {min_priority}.")
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = self.settings.SMTP_USERNAME
            msg['To'] = self.settings.ALERT_EMAIL
            msg['Subject'] = f"🚀 {data['priority']} Crypto Alert: {data['symbol']} at ${data['current_price']:.2f}"

            ai_text = "N/A"
            if 'ai_analysis' in data and data['ai_analysis']:
                ai = data['ai_analysis']
                ai_text = f"{ai.get('sentiment_label')} - {ai.get('trade_suggestion', {}).get('action')}\nReason: {ai.get('reasoning')}"

            body = f"""
            <html>
            <body>
            <h2>Enterprise Crypto Alert</h2>
            <p><strong>Symbol:</strong> {data['symbol']}</p>
            <p><strong>Price:</strong> ${data['current_price']:.2f}</p>
            <p><strong>Change:</strong> {data['price_change_pct']:.2f}%</p>
            <p><strong>Priority:</strong> {data['priority']}</p>
            <p><strong>Category:</strong> {data.get('category', 'VOLATILITY')}</p>
            <h3>AI Insights</h3>
            <p>{ai_text}</p>
            </body>
            </html>
            """
            msg.attach(MIMEText(body, 'html'))

            password = str(self.settings.SMTP_PASSWORD or "").strip().strip('"').strip("'")
            password = password.replace(" ", "")

            server = smtplib.SMTP(self.settings.SMTP_SERVER, self.settings.SMTP_PORT, timeout=10)
            try:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.settings.SMTP_USERNAME, password)
                server.send_message(msg)
            finally:
                try:
                    server.quit()
                except Exception:
                    pass
            logger.info(f"Email alert sent for {data['symbol']}")
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, ConnectionError) as e:
            logger.warning(f"Could not connect to SMTP server (DNS/Network issue): {e}")
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")

    def send_discord(self, data: dict):
        """Sends alert via Discord Webhook with enterprise format."""
        if not self.settings.DISCORD_WEBHOOK:
            return

        ai_text = "N/A"
        if 'ai_analysis' in data and data['ai_analysis']:
            ai = data['ai_analysis']
            ai_text = f"**{ai.get('sentiment_label')}** - {ai.get('trade_suggestion', {}).get('action')}\n{ai.get('reasoning')}"

        payload = {
            "content": f"🚨 **{data['priority']} Alert: {data['symbol']}**\n"
                       f"Price: `${data['current_price']:.2f}`\n"
                       f"Change: `{data['price_change_pct']:.2f}%`\n"
                       f"Category: `{data.get('category', 'VOLATILITY')}`\n\n"
                       f"🤖 **AI Insight:**\n{ai_text}"
        }
        try:
            requests.post(self.settings.DISCORD_WEBHOOK, json=payload, timeout=5)
            logger.info(f"Discord alert sent for {data['symbol']}")
        except Exception as e:
            logger.error(f"Failed to send Discord alert: {e}")

    def send_slack(self, data: dict):
        if not self.settings.SLACK_WEBHOOK:
            return

        ai_text = "N/A"
        if 'ai_analysis' in data and data['ai_analysis']:
            ai = data['ai_analysis']
            ai_text = f"*{ai.get('sentiment_label')}* - {ai.get('trade_suggestion', {}).get('action')}\n{ai.get('reasoning')}"

        payload = {
            "text": f"🚨 *{data['priority']} Alert: {data['symbol']}*\n"
                    f"Price: `${data['current_price']:.2f}`\n"
                    f"Change: `{data['price_change_pct']:.2f}%`\n"
                    f"Category: `{data.get('category', 'VOLATILITY')}`\n\n"
                    f"🤖 *AI Insight:*\n{ai_text}"
        }
        try:
            requests.post(self.settings.SLACK_WEBHOOK, json=payload, timeout=5)
            logger.info(f"Slack alert sent for {data['symbol']}")
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")

    def save_to_json(self, data: dict):
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.logs_dir / "alerts.json"
        try:
            alerts = []
            if file_path.exists():
                with file_path.open("r", encoding="utf-8") as f:
                    try:
                        alerts = json.load(f)
                    except json.JSONDecodeError:
                        alerts = []
            
            # Keep only the last 100 alerts
            alerts.append(data)
            alerts = alerts[-100:]
            
            with file_path.open("w", encoding="utf-8") as f:
                json.dump(alerts, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save alert to JSON: {e}")

    async def broadcast(self, alert_data: dict):
        self.save_to_json(alert_data)
        self.send_console(alert_data)
        self.send_email(alert_data)
        self.send_discord(alert_data)
        self.send_slack(alert_data)
        self.send_telegram(alert_data)
        self.send_sms(alert_data)

    def send_telegram(self, data: dict):
        token = self.settings.TELEGRAM_BOT_TOKEN
        chat_id = self.settings.TELEGRAM_CHAT_ID
        if not token or not chat_id:
            return
        ai_text = "N/A"
        if "ai_analysis" in data and data["ai_analysis"]:
            ai = data["ai_analysis"]
            ai_text = f"*{ai.get('sentiment_label')}* - {ai.get('trade_suggestion', {}).get('action')}\n{ai.get('reasoning')}"
        text = (
            f"🚨 *{data['priority']} Alert: {data['symbol']}*\n"
            f"Price: `${data['current_price']:.2f}`\n"
            f"Change: `{data['price_change_pct']:.2f}%`\n"
            f"Category: `{data.get('category', 'VOLATILITY')}`\n\n"
            f"🤖 *AI Insight:*\n{ai_text}"
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        try:
            requests.post(url, json=payload, timeout=5)
            logger.info(f"Telegram alert sent for {data['symbol']}")
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")

    def send_sms(self, data: dict):
        from_number = self.settings.TWILIO_FROM_NUMBER
        to_number = getattr(self.settings, "TWILIO_TO_NUMBER", "")
        sid = self.settings.TWILIO_ACCOUNT_SID
        token = self.settings.TWILIO_AUTH_TOKEN
        if not from_number or not to_number or not sid or not token:
            return
        priority = data.get("priority", "LOW").upper()
        if priority != "CRITICAL":
            return
        body = (
            f"{data['priority']} Alert {data['symbol']} "
            f"{data['current_price']:.2f} "
            f"{data['price_change_pct']:.2f}%"
        )
        try:
            from twilio.rest import Client
        except Exception:
            return
        try:
            client = Client(sid, token)
            client.messages.create(body=body, from_=from_number, to=to_number)
            logger.info(f"SMS alert sent for {data['symbol']}")
        except Exception as e:
            logger.error(f"Failed to send SMS alert: {e}")
