"""LLM-based analysis utilities used to enrich alerts with sentiment and predictions."""

import logging
import asyncio
import time
import json
from typing import Dict, Optional, Any
import re

# Optional enterprise clients
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

logger = logging.getLogger(__name__)

class EnterpriseAIAnalyzer:
    """
    Multi-model AI Analyzer supporting Gemini, GPT-4, and Claude.
    Provides sentiment scoring, pattern recognition, and stop-loss suggestions.
    """
    def __init__(self, settings):
        self.settings = settings
        self.cache = {}
        self.last_call_time = 0
        self.gemini = None
        
        # Initialize clients
        if settings.GEMINI_API_KEY:
            try:
                import google.generativeai as genai

                genai.configure(api_key=settings.GEMINI_API_KEY)
                model_name = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")
                self.gemini = genai.GenerativeModel(model_name)
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
                self.gemini = None
        
        self.openai = OpenAI(api_key=settings.OPENAI_API_KEY) if OpenAI and getattr(settings, "OPENAI_API_KEY", "") else None
        self.openrouter = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        ) if OpenAI and getattr(settings, "OPENROUTER_API_KEY", "") else None
        self.anthropic = Anthropic(api_key=settings.ANTHROPIC_API_KEY) if Anthropic and getattr(settings, "ANTHROPIC_API_KEY", "") else None

    async def _call_gemini(self, prompt: str) -> str:
        response = await asyncio.to_thread(self.gemini.generate_content, prompt)
        return response.text

    async def _call_gpt4(self, prompt: str) -> str:
        response = await asyncio.to_thread(
            self.openai.chat.completions.create,
            model="gpt-4-turbo-preview",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content

    async def _call_claude(self, prompt: str) -> str:
        response = await asyncio.to_thread(
            self.anthropic.messages.create,
            model="claude-3-opus-20240229",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    async def analyze_alert(self, alert_data: dict) -> dict:
        prompt = f"""
        Analyze this crypto alert for {alert_data['symbol']}:
        - Price: ${alert_data['current_price']:.2f}
        - Change: {alert_data['price_change_pct']:.2f}%
        - Priority: {alert_data['priority']}
        - Category: {alert_data.get('category', 'N/A')}
        - Indicators: {json.dumps(alert_data['indicators'])}
        - Patterns: {json.dumps(alert_data.get('patterns', []))}
        - Levels: {json.dumps(alert_data.get('levels', {}))}
        - Conditional Rule: {alert_data.get('conditional_rule', 'None')}

        Provide an enterprise-grade analysis including:
        1. Sentiment Score (0-100)
        2. Trade Action (BUY/SELL/HOLD)
        3. Stop-Loss and Take-Profit suggestions
        4. Volume analysis (is this move backed by volume surge or exhaustion?)
        5. Prediction tracking (estimated price in 1h, 4h, and 24h)
        6. Specific Pattern confirmation: Look for Head & Shoulders (H&S), Cup & Handle, Triangles, or Double Top/Bottom.
        7. News sentiment context: Provide a simulated sentiment score (-1 to 1) based on current price action and common market narratives.
        8. Support and Resistance: Identify the next major auto support and resistance levels.

        Return ONLY a JSON object with keys: 
        sentiment_score, sentiment_label, reasoning, 
        trade_suggestion (action, stop_loss, take_profit), 
        volume_analysis, predictions (1h, 4h, 24h), 
        patterns_confirmed (list of patterns found),
        news_sentiment_score,
        levels (support, resistance),
        1h_prediction, 24h_prediction, confidence.

        CRITICAL: All price-related values (stop_loss, take_profit, predictions, support, resistance, 1h_prediction, 24h_prediction) MUST be single numeric values (float/int) without currency symbols or text description.
        """

        analysis = None

        if not analysis and self.openrouter:
            try:
                response = self.openrouter.chat.completions.create(
                    model=self.settings.DEFAULT_AI_MODEL,
                    messages=[{"role": "user", "content": prompt}]
                )
                analysis = self._parse_json(response.choices[0].message.content, alert_data)
            except Exception as e:
                logger.error(f"OpenRouter analysis failed: {e}")

        if not analysis and self.openai:
            try:
                response = self.openai.chat.completions.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}]
                )
                analysis = self._parse_json(response.choices[0].message.content, alert_data)
            except Exception as e:
                logger.error(f"OpenAI analysis failed: {e}")

        if not analysis and self.anthropic:
            try:
                response = self.anthropic.messages.create(
                    model="claude-3-opus-20240229",
                    max_tokens=1000,
                    messages=[{"role": "user", "content": prompt}]
                )
                analysis = self._parse_json(response.content[0].text, alert_data)
            except Exception as e:
                logger.error(f"Claude analysis failed: {e}")

        if not analysis:
            analysis = self._mock_analysis(alert_data)

        try:
            ensemble = await self.get_ensemble_prediction(alert_data)
        except Exception as e:
            logger.error(f"Ensemble prediction failed: {e}")
            ensemble = None
        if ensemble:
            ts = analysis.get("trade_suggestion") or {}
            if not isinstance(ts, dict):
                ts = {}
            ts_action = ts.get("action")
            if not ts_action or ts_action == "HOLD":
                ts["action"] = ensemble.get("action", ts_action or "HOLD")
            analysis["trade_suggestion"] = ts
            analysis["ensemble"] = ensemble

        try:
            extra = await self.get_price_prediction(alert_data["symbol"], alert_data["current_price"])
        except Exception as e:
            logger.error(f"Gemini price prediction failed: {e}")
            extra = None
        if extra:
            preds = analysis.get("predictions") or {}
            if not isinstance(preds, dict):
                preds = {}
            preds["1h"] = extra.get("1h_prediction", alert_data["current_price"])
            preds["24h"] = extra.get("24h_prediction", alert_data["current_price"])
            analysis["predictions"] = preds
            analysis["prediction_confidence"] = extra.get("confidence", 0.5)
        return analysis

    async def get_price_prediction(self, symbol: str, current_price: float) -> Dict[str, float]:
        if not getattr(self, "gemini", None):
            return {
                "1h_prediction": float(current_price * 1.01),
                "24h_prediction": float(current_price * 1.03),
                "confidence": 0.5,
            }
        prompt = f"""
        You are a quantitative crypto analyst.
        Current price for {symbol} is {current_price:.2f}.
        Return ONLY JSON with keys: 1h_prediction, 24h_prediction, confidence.
        1h_prediction: predicted price in 1 hour as float.
        24h_prediction: predicted price in 24 hours as float.
        confidence: number between 0 and 1 representing forecast confidence.
        """
        try:
            text = await self._call_gemini(prompt)
            clean = text.strip().replace("```json", "").replace("```", "")
            data = json.loads(clean)
        except Exception:
            return {
                "1h_prediction": float(current_price),
                "24h_prediction": float(current_price),
                "confidence": 0.5,
            }
        one_h = self._to_float(data.get("1h_prediction"), fallback=current_price)
        day = self._to_float(data.get("24h_prediction"), fallback=current_price)
        conf = self._to_float(data.get("confidence"), fallback=0.5)
        if conf > 1:
            conf = conf / 100.0
        conf = max(0.0, min(conf, 1.0))
        return {
            "1h_prediction": one_h,
            "24h_prediction": day,
            "confidence": conf,
        }

    def analyze_market(self, symbol: str, price: float, df) -> Dict[str, Any]:
        snapshot = {}
        try:
            if df is not None and not df.empty:
                last = df.iloc[-1]
                snapshot = {
                    "close": float(last.get("close", price)),
                    "rsi": float(last.get("RSI_14", 50)),
                    "volume": float(last.get("volume", 0)),
                }
        except Exception:
            snapshot = {}
        prompt = f"""
        You are an enterprise crypto trading assistant.
        Analyze {symbol} with current price {price:.2f}.
        Latest indicators: {json.dumps(snapshot)}.
        Return ONLY JSON with keys: action and confidence.
        action must be one of BUY, SELL, HOLD.
        confidence must be a number between 0 and 100.
        """
        models = {}
        g = self._call_gemini_action(prompt)
        if g:
            models["gemini"] = g
        l = self._call_llama(prompt)
        if l:
            models["llama"] = l
        q = self._call_qwen(prompt)
        if q:
            models["qwen"] = q
        consensus = self._build_consensus(models)
        return {"models": models, "consensus": consensus}

    def _call_gemini_action(self, prompt: str) -> Dict[str, Any]:
        if not getattr(self, "gemini", None):
            return {}
        try:
            response = self.gemini.generate_content(prompt)
            text = response.text or ""
            clean = text.strip().replace("```json", "").replace("```", "")
            data = json.loads(clean)
        except Exception as e:
            logger.error(f"Gemini market call failed: {e}")
            return {}
        action = str(data.get("action", "")).upper().strip()
        conf = self._to_float(data.get("confidence"), fallback=50.0)
        return {"action": action, "confidence": conf}

    def _call_llama(self, prompt: str) -> Dict[str, Any]:
        if not self.openrouter:
            return {}
        try:
            response = self.openrouter.chat.completions.create(
                model="meta-llama/llama-3.3-70b-instruct:free",
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.choices[0].message.content
            clean = text.strip().replace("```json", "").replace("```", "")
            data = json.loads(clean)
        except Exception as e:
            logger.error(f"Llama market call failed: {e}")
            return {}
        action = str(data.get("action", "")).upper().strip()
        conf = self._to_float(data.get("confidence"), fallback=50.0)
        return {"action": action, "confidence": conf}

    def _call_qwen(self, prompt: str) -> Dict[str, Any]:
        if not self.openrouter:
            return {}
        try:
            response = self.openrouter.chat.completions.create(
                model="qwen/qwen-2.5-72b-instruct:free",
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.choices[0].message.content
            clean = text.strip().replace("```json", "").replace("```", "")
            data = json.loads(clean)
        except Exception as e:
            logger.error(f"Qwen market call failed: {e}")
            return {}
        action = str(data.get("action", "")).upper().strip()
        conf = self._to_float(data.get("confidence"), fallback=50.0)
        return {"action": action, "confidence": conf}

    def _build_consensus(self, models: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        if not models:
            return {}
        counts = {}
        total_conf = 0.0
        n = 0
        for data in models.values():
            action = str(data.get("action", "")).upper().strip()
            if action not in ("BUY", "SELL", "HOLD"):
                continue
            counts[action] = counts.get(action, 0) + 1
            total_conf += float(data.get("confidence", 50.0))
            n += 1
        if not counts or n == 0:
            return {}
        best_action = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
        avg_conf = total_conf / n
        return {"action": best_action, "confidence": avg_conf}

    async def get_ensemble_prediction(self, alert_data: dict) -> Dict[str, Any]:
        if not self.openrouter:
            return {}
        models = [
            "google/gemini-2.0-flash-exp:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "qwen/qwen-2.5-72b-instruct:free",
        ]
        prompt = f"""
        You are part of an AI trading ensemble.
        Analyze this crypto alert for {alert_data['symbol']} with current price {alert_data['current_price']:.2f}
        and {alert_data['price_change_pct']:.4f}% change.

        Indicators: {json.dumps(alert_data.get('indicators', {}))}
        Levels: {json.dumps(alert_data.get('levels', {}))}
        Patterns: {json.dumps(alert_data.get('patterns', []))}

        Return ONLY a JSON object with:
        - action: one of "BUY", "SELL", "HOLD"
        - confidence: number between 0 and 1
        - reasoning: short explanation
        """
        votes = []
        for model in models:
            try:
                response = await asyncio.to_thread(
                    self.openrouter.chat.completions.create,
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.choices[0].message.content
                clean = text.strip().replace("```json", "").replace("```", "")
                data = json.loads(clean)
                action = str(data.get("action", "")).upper().strip()
                if action not in ("BUY", "SELL", "HOLD"):
                    continue
                conf = self._to_float(data.get("confidence"), fallback=0.5)
                if conf > 1:
                    conf = conf / 100.0
                conf = max(0.0, min(conf, 1.0))
                votes.append(
                    {
                        "model": model,
                        "action": action,
                        "confidence": conf,
                        "reasoning": str(data.get("reasoning", "")),
                    }
                )
            except Exception as e:
                logger.error(f"Ensemble call failed for {model}: {e}")
                continue
        if not votes:
            return {}
        counts = {}
        for v in votes:
            counts[v["action"]] = counts.get(v["action"], 0) + 1
        best_action = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
        avg_conf = sum(v["confidence"] for v in votes) / len(votes)
        reasons = [f"[{v['model']}] {v['reasoning']}" for v in votes if v.get("reasoning")]
        reasoning = " | ".join(reasons)
        return {
            "action": best_action,
            "confidence": avg_conf,
            "votes": votes,
            "reasoning": reasoning,
        }

    def _mock_analysis(self, alert_data: dict) -> dict:
        """Deterministic mock analysis for when APIs are unavailable."""
        score = 50 + (alert_data['price_change_pct'] * 2)
        score = min(max(score, 0), 100)
        price = alert_data['current_price']
        
        return {
            "sentiment_score": int(score),
            "sentiment_label": "Bullish" if score > 50 else "Bearish",
            "reasoning": f"Price surge of {alert_data['price_change_pct']:.2f}% detected with strong indicator support.",
            "trade_suggestion": {
                "action": "BUY" if score > 60 else ("SELL" if score < 40 else "HOLD"),
                "stop_loss": price * 0.98,
                "take_profit": price * 1.05
            },
            "volume_analysis": "Volume surge confirms the breakout trend.",
            "predictions": {
                "1h": price * 1.01,
                "4h": price * 1.02,
                "24h": price * 1.05
            },
            "patterns_confirmed": ["Cup & Handle", "Breakout"],
            "news_sentiment_score": 0.65,
            "levels": {
                "support": price * 0.95,
                "resistance": price * 1.08
            }
        }

    def _parse_json(self, text: str, alert_data: dict) -> Optional[dict]:
        """Helper to extract, parse, and normalize JSON from AI responses."""
        try:
            clean_json = text.strip().replace('```json', '').replace('```', '')
            data = json.loads(clean_json)
        except Exception:
            return None
        return self._normalize_analysis(data, alert_data)

    def _normalize_analysis(self, analysis: Dict[str, Any], alert_data: dict) -> Dict[str, Any]:
        """Normalize AI response into a consistent numeric structure."""
        if not isinstance(analysis, dict):
            return self._mock_analysis(alert_data)

        # Sentiment defaults
        analysis.setdefault("sentiment_score", 50)
        analysis.setdefault("sentiment_label", "Neutral")
        analysis.setdefault("reasoning", "")

        # Trade suggestion normalization
        ts = analysis.get("trade_suggestion") or {}
        if not isinstance(ts, dict):
            ts = {}
        ts.setdefault("action", "HOLD")
        ts.setdefault("stop_loss", alert_data["current_price"] * 0.98)
        ts.setdefault("take_profit", alert_data["current_price"] * 1.05)
        analysis["trade_suggestion"] = ts

        preds = analysis.get("predictions")
        if not isinstance(preds, dict):
            preds = {}
        for horizon in ("1h", "4h", "24h"):
            if horizon not in preds:
                alts = (
                    f"{horizon}_prediction",
                    f"prediction_{horizon}",
                    f"pred_{horizon}",
                    f"price_{horizon}",
                )
                for alt in alts:
                    if alt in analysis:
                        preds[horizon] = analysis[alt]
                        break
        preds = {
            k: self._to_float(v, fallback=alert_data["current_price"])
            for k, v in preds.items()
            if k in ("1h", "4h", "24h")
        }
        analysis["predictions"] = preds

        levels = analysis.get("levels")
        if not isinstance(levels, dict):
            levels = {}
        alert_levels = alert_data.get("levels") or {}
        if "support" not in levels and "support" in alert_levels:
            levels["support"] = alert_levels["support"]
        if "resistance" not in levels and "resistance" in alert_levels:
            levels["resistance"] = alert_levels["resistance"]
        for key in ("support", "resistance"):
            if key in levels:
                levels[key] = self._to_float(levels[key], fallback=alert_data["current_price"])
        analysis["levels"] = levels

        if not analysis.get("patterns_confirmed"):
            pf = analysis.get("patterns_found")
            if isinstance(pf, list):
                analysis["patterns_confirmed"] = pf
            else:
                alert_patterns = alert_data.get("patterns")
                if isinstance(alert_patterns, list):
                    analysis["patterns_confirmed"] = alert_patterns
                else:
                    analysis.setdefault("patterns_confirmed", [])
        analysis.setdefault("volume_analysis", "")
        analysis.setdefault("news_sentiment_score", 0.0)

        return analysis

    def _to_float(self, value: Any, fallback: float = 0.0) -> float:
        """Convert any value to float, extracting first number from strings if needed."""
        if isinstance(value, (int, float)):
            return float(value)
        try:
            text = str(value)
            match = re.search(r"[-+]?\d*\.?\d+", text.replace(",", ""))
            if match:
                return float(match.group())
        except Exception:
            pass
        return float(fallback)
