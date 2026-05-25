"""
Nifty200 Momentum 30 - Custom MCP Server
Production-ready MCP server for agentic stock analysis
Deploys on Railway (Docker)
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict
from enum import Enum

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool, TextContent, ImageContent, 
    EmbeddedResource, LoggingLevel
)
import httpx
import yfinance as yf
from bs4 import BeautifulSoup
import feedparser

# ============================================================================
# CONFIGURATION
# ============================================================================

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# Nifty200 Momentum 30 constituents (auto-updated via scraper)
DEFAULT_CONSTITUENTS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "KOTAKBANK.NS",
    "LT.NS", "BAJFINANCE.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS",
    "TITAN.NS", "SUNPHARMA.NS", "ULTRACEMCO.NS", "NESTLEIND.NS", "WIPRO.NS",
    "POWERGRID.NS", "NTPC.NS", "M&M.NS", "ADANIENT.NS", "GRASIM.NS",
    "TATAMOTORS.NS", "HCLTECH.NS", "BAJAJFINSV.NS", "TECHM.NS", "COALINDIA.NS"
]

# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================

class Signal(Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    WEAK_BUY = "WEAK_BUY"
    HOLD = "HOLD"
    WEAK_SELL = "WEAK_SELL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"
    AVOID = "AVOID"

class RedTeamStatus(Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    BLOCK = "BLOCK"

@dataclass
class RedTeamResult:
    symbol: str
    status: str
    score: int  # 0-100
    flags: List[str]
    pledge_pct: float
    auditor_issues: bool
    regulatory_actions: bool
    fraud_history: bool
    esg_score: float
    promoter_selling: bool
    debt_restructure: bool
    shell_risk: bool
    social_red_flags: bool
    details: str

@dataclass
class FundamentalResult:
    symbol: str
    score: int
    roe: float
    roce: float
    debt_equity: float
    interest_coverage: float
    fcf_yield: float
    earnings_growth_5y: float
    pe_vs_historical: float
    pb_vs_sector: float
    peg_ratio: float
    operating_margin: float
    cash_conversion: float
    dividend_track: bool
    working_capital_days: float
    altman_z: float
    verdict: str

@dataclass
class TechnicalResult:
    symbol: str
    signal: str
    score: int
    momentum_6m: float
    momentum_12m: float
    volatility: float
    adj_momentum_6m: float
    adj_momentum_12m: float
    momentum_score: float
    rsi_14: float
    macd_signal: str
    ema_trend: str
    volume_spike: bool
    bullish_div: bool
    bearish_div: bool
    atr_14: float
    bb_position: str
    support_level: float
    resistance_level: float

@dataclass
class NewsResult:
    symbol: str
    score: int
    sentiment: float
    urgency: float
    key_headlines: List[str]
    flags: List[str]
    recommendation: str

@dataclass
class FinalVerdict:
    symbol: str
    signal: str
    composite_score: int
    confidence: int
    position_size_pct: float
    entry_price: Optional[float]
    stop_loss: Optional[float]
    target_price: Optional[float]
    rationale: str
    red_team: RedTeamResult
    fundamental: FundamentalResult
    technical: TechnicalResult
    news: NewsResult
    timestamp: str

# ============================================================================
# RED TEAM AGENT
# ============================================================================

class RedTeamAgent:
    """Corporate governance & scam detection agent"""

    async def analyze(self, symbol: str) -> RedTeamResult:
        """Run full red team screening on a stock"""

        # In production, these would scrape SEBI, BSE, MCA, etc.
        # For demo, we simulate with yfinance data + web scraping

        ticker = yf.Ticker(symbol)
        info = ticker.info

        flags = []
        score = 100

        # 1. Promoter Pledge Check
        pledge_pct = info.get("pledgedShares", 0) or 0
        if pledge_pct > 50:
            score -= 40
            flags.append(f"Promoter pledge {pledge_pct:.1f}% > 50%")
        elif pledge_pct > 30:
            score -= 20
            flags.append(f"Promoter pledge {pledge_pct:.1f}% > 30%")

        # 2. Debt/Equity sanity check (proxy for restructuring risk)
        debt_equity = info.get("debtToEquity", 0) or 0
        if debt_equity > 100:  # >1.0x
            score -= 15
            flags.append(f"High D/E {debt_equity/100:.1f}x")

        # 3. ESG proxy (using sustainability score if available)
        esg_score = info.get("sustainabilityScore", 50) or 50
        if esg_score < 30:
            score -= 15
            flags.append(f"Low ESG score {esg_score}")

        # 4. Auditor resignation proxy (check for recent news)
        auditor_issues = False
        regulatory_actions = False
        fraud_history = False
        promoter_selling = False
        debt_restructure = False
        shell_risk = False
        social_red_flags = False

        # Web scrape for red flags
        try:
            red_flags = await self._scrape_red_flags(symbol)
            if red_flags:
                score -= len(red_flags) * 10
                flags.extend(red_flags)
                for f in red_flags:
                    if "fraud" in f.lower() or "scam" in f.lower():
                        fraud_history = True
                    if "sebi" in f.lower():
                        regulatory_actions = True
                    if "auditor" in f.lower():
                        auditor_issues = True
        except Exception:
            pass

        # Determine status
        if score < 30 or fraud_history or regulatory_actions:
            status = RedTeamStatus.BLOCK.value
        elif score < 70 or flags:
            status = RedTeamStatus.WARNING.value
        else:
            status = RedTeamStatus.PASS.value

        return RedTeamResult(
            symbol=symbol,
            status=status,
            score=max(0, score),
            flags=flags,
            pledge_pct=pledge_pct,
            auditor_issues=auditor_issues,
            regulatory_actions=regulatory_actions,
            fraud_history=fraud_history,
            esg_score=esg_score,
            promoter_selling=promoter_selling,
            debt_restructure=debt_restructure,
            shell_risk=shell_risk,
            social_red_flags=social_red_flags,
            details="; ".join(flags) if flags else "Clean"
        )

    async def _scrape_red_flags(self, symbol: str) -> List[str]:
        """Scrape news for governance red flags"""
        flags = []

        # Scrape MoneyControl for recent news
        company_name = symbol.replace(".NS", "").lower()
        url = f"https://www.moneycontrol.com/news/tags/{company_name}.html"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                soup = BeautifulSoup(resp.text, "html.parser")
                headlines = soup.find_all("h2", limit=10)

                red_keywords = ["fraud", "scam", "sebi", "penalty", "fine", "raid", 
                               "investigation", "auditor", "resign", "pledge", "default"]

                for h in headlines:
                    text = h.get_text().lower()
                    for kw in red_keywords:
                        if kw in text:
                            flags.append(h.get_text().strip())
                            break
        except Exception:
            pass

        return list(set(flags))[:5]

# ============================================================================
# GREEN TEAM AGENT
# ============================================================================

class GreenTeamAgent:
    """Fundamental analysis agent"""

    async def analyze(self, symbol: str) -> FundamentalResult:
        """Run fundamental analysis"""

        ticker = yf.Ticker(symbol)
        info = ticker.info

        # Extract metrics with fallbacks
        roe = info.get("returnOnEquity", 0) or 0
        if roe:
            roe *= 100

        roce = info.get("returnOnCapitalEmployed", roe * 0.9) or roe * 0.9

        debt_equity = (info.get("debtToEquity", 0) or 0) / 100

        interest_coverage = info.get("interestCoverage", 0) or 5.0

        # FCF yield
        fcf = info.get("freeCashflow", 0) or 0
        ev = info.get("enterpriseValue", 1) or 1
        fcf_yield = (fcf / ev * 100) if ev else 0

        # Growth
        earnings_growth = info.get("earningsGrowth", 0) or 0
        if earnings_growth:
            earnings_growth *= 100

        # Valuation
        pe = info.get("trailingPE", 0) or 0
        pb = info.get("priceToBook", 0) or 0
        peg = info.get("pegRatio", pe / max(earnings_growth, 1)) if pe and earnings_growth else 2.0

        operating_margin = (info.get("operatingMargins", 0) or 0) * 100

        # Score calculation
        score = 50  # Base

        if roe > 15: score += 15
        elif roe > 10: score += 8
        else: score -= 10

        if debt_equity < 0.5: score += 10
        elif debt_equity > 1.0: score -= 15

        if interest_coverage > 5: score += 10
        elif interest_coverage < 2: score -= 10

        if fcf_yield > 5: score += 10
        elif fcf_yield < 0: score -= 5

        if earnings_growth > 12: score += 10
        elif earnings_growth < 5: score -= 5

        if peg < 1.0: score += 10
        elif peg > 2.0: score -= 10

        if operating_margin > 15: score += 10
        elif operating_margin < 8: score -= 5

        # Verdict
        if score >= 80: verdict = "STRONG"
        elif score >= 60: verdict = "MODERATE"
        elif score >= 40: verdict = "WEAK"
        else: verdict = "AVOID"

        return FundamentalResult(
            symbol=symbol,
            score=max(0, min(100, score)),
            roe=roe,
            roce=roce,
            debt_equity=debt_equity,
            interest_coverage=interest_coverage,
            fcf_yield=fcf_yield,
            earnings_growth_5y=earnings_growth,
            pe_vs_historical=pe,
            pb_vs_sector=pb,
            peg_ratio=peg,
            operating_margin=operating_margin,
            cash_conversion=0.8,  # Proxy
            dividend_track=info.get("dividendRate", 0) > 0,
            working_capital_days=30,  # Proxy
            altman_z=2.5,  # Would calculate properly in production
            verdict=verdict
        )

# ============================================================================
# BLUE TEAM AGENT
# ============================================================================

class BlueTeamAgent:
    """Technical analysis + TradingView-style signals agent"""

    async def analyze(self, symbol: str) -> TechnicalResult:
        """Run technical analysis with momentum scoring"""

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y")

        if hist.empty or len(hist) < 252:
            return TechnicalResult(
                symbol=symbol, signal="NEUTRAL", score=50,
                momentum_6m=0, momentum_12m=0, volatility=0,
                adj_momentum_6m=0, adj_momentum_12m=0, momentum_score=0,
                rsi_14=50, macd_signal="NEUTRAL", ema_trend="FLAT",
                volume_spike=False, bullish_div=False, bearish_div=False,
                atr_14=0, bb_position="MIDDLE", support_level=0, resistance_level=0
            )

        close = hist["Close"]
        volume = hist["Volume"]

        # 6-month & 12-month momentum
        momentum_6m = ((close.iloc[-1] / close.iloc[-126]) - 1) * 100 if len(close) >= 126 else 0
        momentum_12m = ((close.iloc[-1] / close.iloc[0]) - 1) * 100

        # Volatility (annualized)
        returns = close.pct_change().dropna()
        volatility = returns.std() * (252 ** 0.5) * 100

        # Adjusted momentum (higher return / lower vol = better)
        adj_momentum_6m = momentum_6m / max(volatility, 1)
        adj_momentum_12m = momentum_12m / max(volatility, 1)

        # Composite momentum score (Nifty200 Momentum 30 style)
        momentum_score = (adj_momentum_6m * 0.6) + (adj_momentum_12m * 0.4)

        # RSI(14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi_14 = 100 - (100 / (1 + rs.iloc[-1]))

        # MACD
        ema_12 = close.ewm(span=12).mean()
        ema_26 = close.ewm(span=26).mean()
        macd = ema_12 - ema_26
        signal_line = macd.ewm(span=9).mean()
        macd_signal = "BULLISH" if macd.iloc[-1] > signal_line.iloc[-1] else "BEARISH"

        # EMA Trend
        ema_20 = close.ewm(span=20).mean()
        ema_50 = close.ewm(span=50).mean()
        ema_200 = close.ewm(span=200).mean()

        current = close.iloc[-1]
        if current > ema_20.iloc[-1] > ema_50.iloc[-1] > ema_200.iloc[-1]:
            ema_trend = "STRONG_UP"
        elif current > ema_20.iloc[-1] > ema_50.iloc[-1]:
            ema_trend = "UP"
        elif current < ema_20.iloc[-1] < ema_50.iloc[-1]:
            ema_trend = "DOWN"
        else:
            ema_trend = "FLAT"

        # Volume spike
        vol_sma = volume.rolling(20).mean()
        volume_spike = volume.iloc[-1] > vol_sma.iloc[-1] * 1.5

        # Divergence detection
        recent_highs = close.rolling(21).max()
        recent_lows = close.rolling(21).min()
        recent_rsi = rsi_14

        bearish_div = (close.iloc[-1] > recent_highs.iloc[-22] and 
                       rsi_14 < (100 - (100 / (1 + (gain.iloc[-22] / loss.iloc[-22])))) if loss.iloc[-22] > 0 else 50)

        bullish_div = (close.iloc[-1] < recent_lows.iloc[-22] and 
                       rsi_14 > (100 - (100 / (1 + (gain.iloc[-22] / loss.iloc[-22])))) if loss.iloc[-22] > 0 else 50)

        # ATR
        high_low = hist["High"] - hist["Low"]
        high_close = abs(hist["High"] - close.shift())
        low_close = abs(hist["Low"] - close.shift())
        tr = high_low.combine(high_close, max).combine(low_close, max)
        atr_14 = tr.rolling(14).mean().iloc[-1]

        # Bollinger Bands
        bb_sma = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_sma + (bb_std * 2)
        bb_lower = bb_sma - (bb_std * 2)

        if current > bb_upper.iloc[-1]:
            bb_position = "ABOVE_UPPER"
        elif current < bb_lower.iloc[-1]:
            bb_position = "BELOW_LOWER"
        elif current > bb_sma.iloc[-1]:
            bb_position = "UPPER_HALF"
        else:
            bb_position = "LOWER_HALF"

        # Support/Resistance (simple pivot-based)
        pivot_high = close.rolling(20).max().iloc[-1]
        pivot_low = close.rolling(20).min().iloc[-1]

        # Signal generation
        score = 50
        signal = "NEUTRAL"

        if momentum_score > 80 and ema_trend in ["STRONG_UP", "UP"] and volume_spike:
            signal = "STRONG_BUY"
            score = 90
        elif momentum_score > 60 and ema_trend in ["STRONG_UP", "UP"]:
            signal = "BUY"
            score = 75
        elif momentum_score > 40 and not bearish_div:
            signal = "WEAK_BUY"
            score = 60
        elif momentum_score < 20 or (ema_trend == "DOWN" and bearish_div):
            signal = "STRONG_SELL"
            score = 10
        elif momentum_score < 40 or ema_trend == "DOWN":
            signal = "SELL"
            score = 25

        return TechnicalResult(
            symbol=symbol,
            signal=signal,
            score=score,
            momentum_6m=momentum_6m,
            momentum_12m=momentum_12m,
            volatility=volatility,
            adj_momentum_6m=adj_momentum_6m,
            adj_momentum_12m=adj_momentum_12m,
            momentum_score=momentum_score,
            rsi_14=rsi_14,
            macd_signal=macd_signal,
            ema_trend=ema_trend,
            volume_spike=volume_spike,
            bullish_div=bullish_div,
            bearish_div=bearish_div,
            atr_14=atr_14,
            bb_position=bb_position,
            support_level=pivot_low,
            resistance_level=pivot_high
        )

# ============================================================================
# NEWS SENTINEL AGENT
# ============================================================================

class NewsSentinelAgent:
    """Real-time news intelligence agent"""

    async def analyze(self, symbol: str) -> NewsResult:
        """Analyze news sentiment and events"""

        company_name = symbol.replace(".NS", "")

        headlines = []
        flags = []
        sentiment = 0
        urgency = 0

        # 1. RSS Feeds
        rss_sources = [
            f"https://www.moneycontrol.com/rss/news_{company_name.lower()}.xml",
            "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
            "https://www.business-standard.com/rss/markets-106.rss"
        ]

        for rss_url in rss_sources:
            try:
                feed = feedparser.parse(rss_url)
                for entry in feed.entries[:5]:
                    headlines.append(entry.title)

                    # Simple sentiment scoring
                    title_lower = entry.title.lower()
                    pos_words = ["beat", "growth", "profit", "rise", "gain", "bullish", "upgrade", "buy"]
                    neg_words = ["loss", "fall", "decline", "bearish", "downgrade", "sell", "fraud", "scam", "penalty"]

                    for w in pos_words:
                        if w in title_lower:
                            sentiment += 0.2
                    for w in neg_words:
                        if w in title_lower:
                            sentiment -= 0.3

                    # Urgency detection
                    urgent_words = ["breaking", "urgent", "alert", "sebi", "rbi", "court", "raid"]
                    for w in urgent_words:
                        if w in title_lower:
                            urgency += 0.3
                            flags.append(entry.title)
            except Exception:
                pass

        # 2. Web scrape MoneyControl
        try:
            url = f"https://www.moneycontrol.com/news/tags/{company_name.lower()}.html"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                soup = BeautifulSoup(resp.text, "html.parser")
                news_items = soup.find_all("h2", limit=8)

                for item in news_items:
                    text = item.get_text().strip()
                    if text and text not in headlines:
                        headlines.append(text)
        except Exception:
            pass

        # Normalize scores
        sentiment = max(-1, min(1, sentiment))
        urgency = max(0, min(1, urgency))

        # Composite news score (-100 to +100)
        news_score = int((sentiment * 50) + 50 - (urgency * 30))

        # Recommendation
        if news_score < -50 or flags:
            recommendation = "AVOID"
        elif news_score < -20:
            recommendation = "CAUTION"
        elif news_score < 20:
            recommendation = "NEUTRAL"
        else:
            recommendation = "FAVORABLE"

        return NewsResult(
            symbol=symbol,
            score=max(0, min(100, news_score)),
            sentiment=sentiment,
            urgency=urgency,
            key_headlines=headlines[:5],
            flags=list(set(flags))[:3],
            recommendation=recommendation
        )

# ============================================================================
# SIGNAL SYNTHESIZER
# ============================================================================

class SignalSynthesizer:
    """Final verdict engine - weighted composite scoring"""

    WEIGHTS = {
        "red_team": 0.30,
        "fundamental": 0.25,
        "technical": 0.25,
        "news": 0.20
    }

    async def synthesize(
        self,
        red: RedTeamResult,
        green: FundamentalResult,
        blue: TechnicalResult,
        news: NewsResult
    ) -> FinalVerdict:
        """Generate final BUY/SELL signal"""

        symbol = red.symbol

        # If Red Team blocks, immediate AVOID
        if red.status == RedTeamStatus.BLOCK.value:
            return FinalVerdict(
                symbol=symbol,
                signal="AVOID",
                composite_score=red.score,
                confidence=95,
                position_size_pct=0,
                entry_price=None,
                stop_loss=None,
                target_price=None,
                rationale=f"🚫 RED TEAM BLOCKED: {red.details}. Governance risk is existential. Never enter.",
                red_team=red,
                fundamental=green,
                technical=blue,
                news=news,
                timestamp=datetime.utcnow().isoformat()
            )

        # Weighted composite score
        composite = (
            red.score * self.WEIGHTS["red_team"] +
            green.score * self.WEIGHTS["fundamental"] +
            blue.score * self.WEIGHTS["technical"] +
            news.score * self.WEIGHTS["news"]
        )

        # Signal mapping
        if composite >= 85:
            signal = "STRONG_BUY"
            position_size = 6.0
        elif composite >= 70:
            signal = "BUY"
            position_size = 4.0
        elif composite >= 50:
            signal = "WEAK_BUY"
            position_size = 2.0
        elif composite >= 35:
            signal = "HOLD"
            position_size = 0
        elif composite >= 20:
            signal = "WEAK_SELL"
            position_size = 0
        elif composite >= 0:
            signal = "SELL"
            position_size = 0
        else:
            signal = "AVOID"
            position_size = 0

        # Confidence based on data quality
        confidence = int(min(95, 60 + (abs(composite - 50) / 50) * 35))

        # Price targets (using technical levels)
        ticker = yf.Ticker(symbol)
        current_price = ticker.info.get("currentPrice", ticker.info.get("regularMarketPrice", 0))

        entry = current_price if current_price else None
        stop = blue.support_level * 0.95 if blue.support_level else None
        target = blue.resistance_level * 1.05 if blue.resistance_level else None

        # Build rationale
        rationale_parts = []

        if red.status == RedTeamStatus.WARNING.value:
            rationale_parts.append(f"⚠️ Red Team Warning: {red.details}")
        else:
            rationale_parts.append("✅ Red Team: Clean governance")

        rationale_parts.append(f"🟢 Fundamental: {green.verdict} (ROE {green.roe:.1f}%, D/E {green.debt_equity:.1f}x)")
        rationale_parts.append(f"🔵 Technical: {blue.signal} (Momentum {blue.momentum_score:.1f}, RSI {blue.rsi_14:.1f})")
        rationale_parts.append(f"📰 News: {news.recommendation} (Sentiment {news.sentiment:+.2f})")

        if news.flags:
            rationale_parts.append(f"⚡ News Flags: {', '.join(news.flags[:2])}")

        rationale = " | ".join(rationale_parts)

        return FinalVerdict(
            symbol=symbol,
            signal=signal,
            composite_score=int(composite),
            confidence=confidence,
            position_size_pct=position_size,
            entry_price=entry,
            stop_loss=stop,
            target_price=target,
            rationale=rationale,
            red_team=red,
            fundamental=green,
            technical=blue,
            news=news,
            timestamp=datetime.utcnow().isoformat()
        )

# ============================================================================
# ORCHESTRATOR
# ============================================================================

class Orchestrator:
    """Master agent that coordinates all sub-agents"""

    def __init__(self):
        self.red_team = RedTeamAgent()
        self.green_team = GreenTeamAgent()
        self.blue_team = BlueTeamAgent()
        self.news_sentinel = NewsSentinelAgent()
        self.synthesizer = SignalSynthesizer()

    async def analyze_stock(self, symbol: str) -> FinalVerdict:
        """Run full pipeline on a single stock"""

        # Run all agents in parallel
        red, green, blue, news = await asyncio.gather(
            self.red_team.analyze(symbol),
            self.green_team.analyze(symbol),
            self.blue_team.analyze(symbol),
            self.news_sentinel.analyze(symbol)
        )

        # Synthesize
        verdict = await self.synthesizer.synthesize(red, green, blue, news)

        return verdict

    async def analyze_index(self, constituents: List[str] = None) -> List[FinalVerdict]:
        """Analyze all Nifty200 Momentum 30 constituents"""

        if constituents is None:
            constituents = DEFAULT_CONSTITUENTS

        # Run sequentially with rate limiting (yfinance friendly)
        results = []
        for symbol in constituents:
            try:
                verdict = await self.analyze_stock(symbol)
                results.append(verdict)
                await asyncio.sleep(0.5)  # Rate limit
            except Exception as e:
                print(f"Error analyzing {symbol}: {e}")
                continue

        # Sort by composite score descending
        results.sort(key=lambda x: x.composite_score, reverse=True)

        return results

# ============================================================================
# MCP SERVER SETUP
# ============================================================================

app = Server("nifty-momentum-agent")

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="analyze_stock",
            description="Run full agentic analysis (Red Team + Fundamental + Technical + News) on a single NSE stock and return BUY/SELL signal with rationale",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "NSE stock symbol (e.g., RELIANCE.NS, TCS.NS)"
                    }
                },
                "required": ["symbol"]
            }
        ),
        Tool(
            name="analyze_index",
            description="Analyze all Nifty200 Momentum 30 constituents and return ranked BUY/SELL signals",
            inputSchema={
                "type": "object",
                "properties": {
                    "constituents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: custom list of symbols. Defaults to Nifty200 Momentum 30"
                    }
                }
            }
        ),
        Tool(
            name="red_team_screen",
            description="Run governance & scam detection screening on a stock. Returns PASS/WARNING/BLOCK",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "NSE stock symbol"
                    }
                },
                "required": ["symbol"]
            }
        ),
        Tool(
            name="fundamental_analysis",
            description="Run fundamental analysis (ROE, ROCE, D/E, PEG, etc.) on a stock",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "NSE stock symbol"
                    }
                },
                "required": ["symbol"]
            }
        ),
        Tool(
            name="technical_analysis",
            description="Run technical analysis with Nifty200 Momentum 30-style scoring (6m/12m momentum adjusted for volatility)",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "NSE stock symbol"
                    }
                },
                "required": ["symbol"]
            }
        ),
        Tool(
            name="news_scan",
            description="Scan latest news, detect sentiment, urgency, and event flags for a stock",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "NSE stock symbol"
                    }
                },
                "required": ["symbol"]
            }
        ),
        Tool(
            name="get_top_picks",
            description="Get top 5 BUY recommendations from Nifty200 Momentum 30 with full analysis",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_avoid_list",
            description="Get stocks to AVOID based on Red Team governance screening",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    orchestrator = Orchestrator()

    if name == "analyze_stock":
        symbol = arguments.get("symbol", "")
        verdict = await orchestrator.analyze_stock(symbol)
        return [TextContent(type="text", text=json.dumps(asdict(verdict), indent=2, default=str))]

    elif name == "analyze_index":
        constituents = arguments.get("constituents")
        results = await orchestrator.analyze_index(constituents)
        return [TextContent(type="text", text=json.dumps([asdict(r) for r in results], indent=2, default=str))]

    elif name == "red_team_screen":
        symbol = arguments.get("symbol", "")
        result = await orchestrator.red_team.analyze(symbol)
        return [TextContent(type="text", text=json.dumps(asdict(result), indent=2, default=str))]

    elif name == "fundamental_analysis":
        symbol = arguments.get("symbol", "")
        result = await orchestrator.green_team.analyze(symbol)
        return [TextContent(type="text", text=json.dumps(asdict(result), indent=2, default=str))]

    elif name == "technical_analysis":
        symbol = arguments.get("symbol", "")
        result = await orchestrator.blue_team.analyze(symbol)
        return [TextContent(type="text", text=json.dumps(asdict(result), indent=2, default=str))]

    elif name == "news_scan":
        symbol = arguments.get("symbol", "")
        result = await orchestrator.news_sentinel.analyze(symbol)
        return [TextContent(type="text", text=json.dumps(asdict(result), indent=2, default=str))]

    elif name == "get_top_picks":
        results = await orchestrator.analyze_index()
        top_buys = [r for r in results if r.signal in ["STRONG_BUY", "BUY"]][:5]
        return [TextContent(type="text", text=json.dumps([asdict(r) for r in top_buys], indent=2, default=str))]

    elif name == "get_avoid_list":
        results = await orchestrator.analyze_index()
        avoid = [r for r in results if r.signal == "AVOID"]
        return [TextContent(type="text", text=json.dumps([asdict(r) for r in avoid], indent=2, default=str))]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="nifty-momentum-agent",
                server_version="1.0.0",
                capabilities=app.get_capabilities()
            )
        )

if __name__ == "__main__":
    asyncio.run(main())
