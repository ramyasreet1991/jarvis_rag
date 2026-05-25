"""
FastAPI HTTP API for the Nifty Momentum Agent
Deploys on Railway (Docker container)
Also exposes MCP tools via HTTP for webapp integration
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import json
import os
from datetime import datetime

from mcp_server.server import (
    Orchestrator, RedTeamAgent, GreenTeamAgent, 
    BlueTeamAgent, NewsSentinelAgent, SignalSynthesizer,
    FinalVerdict, DEFAULT_CONSTITUENTS
)

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Nifty200 Momentum 30 - Agentic Trading API",
    description="Multi-agent stock analysis: Red Team governance screening + Fundamental + Technical + News",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class AnalyzeRequest(BaseModel):
    symbol: str

class AnalyzeIndexRequest(BaseModel):
    constituents: Optional[List[str]] = None

class AnalysisResponse(BaseModel):
    symbol: str
    signal: str
    composite_score: int
    confidence: int
    position_size_pct: float
    entry_price: Optional[float]
    stop_loss: Optional[float]
    target_price: Optional[float]
    rationale: str
    red_team_status: str
    red_team_score: int
    red_team_flags: List[str]
    fundamental_verdict: str
    fundamental_score: int
    roe: float
    debt_equity: float
    peg_ratio: float
    technical_signal: str
    technical_score: int
    momentum_6m: float
    momentum_12m: float
    rsi_14: float
    ema_trend: str
    news_score: int
    news_sentiment: float
    news_recommendation: str
    news_headlines: List[str]
    timestamp: str

class TopPicksResponse(BaseModel):
    picks: List[AnalysisResponse]
    generated_at: str

class AvoidListResponse(BaseModel):
    stocks: List[AnalysisResponse]
    generated_at: str

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def verdict_to_response(v: FinalVerdict) -> AnalysisResponse:
    """Convert internal verdict to API response"""
    return AnalysisResponse(
        symbol=v.symbol,
        signal=v.signal,
        composite_score=v.composite_score,
        confidence=v.confidence,
        position_size_pct=v.position_size_pct,
        entry_price=v.entry_price,
        stop_loss=v.stop_loss,
        target_price=v.target_price,
        rationale=v.rationale,
        red_team_status=v.red_team.status,
        red_team_score=v.red_team.score,
        red_team_flags=v.red_team.flags,
        fundamental_verdict=v.fundamental.verdict,
        fundamental_score=v.fundamental.score,
        roe=v.fundamental.roe,
        debt_equity=v.fundamental.debt_equity,
        peg_ratio=v.fundamental.peg_ratio,
        technical_signal=v.technical.signal,
        technical_score=v.technical.score,
        momentum_6m=v.technical.momentum_6m,
        momentum_12m=v.technical.momentum_12m,
        rsi_14=v.technical.rsi_14,
        ema_trend=v.technical.ema_trend,
        news_score=v.news.score,
        news_sentiment=v.news.sentiment,
        news_recommendation=v.news.recommendation,
        news_headlines=v.news.key_headlines,
        timestamp=v.timestamp
    )

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {
        "service": "Nifty200 Momentum 30 Agentic Trading API",
        "version": "1.0.0",
        "agents": ["Red Team", "Green Team", "Blue Team", "News Sentinel"],
        "endpoints": [
            "/analyze/{symbol}",
            "/analyze-index",
            "/top-picks",
            "/avoid-list",
            "/health"
        ]
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_stock(req: AnalyzeRequest):
    """Run full agentic analysis on a single stock"""
    try:
        orchestrator = Orchestrator()
        verdict = await orchestrator.analyze_stock(req.symbol.upper())
        return verdict_to_response(verdict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze-index", response_model=List[AnalysisResponse])
async def analyze_index(req: AnalyzeIndexRequest):
    """Analyze all Nifty200 Momentum 30 constituents"""
    try:
        orchestrator = Orchestrator()
        results = await orchestrator.analyze_index(req.constituents)
        return [verdict_to_response(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/top-picks", response_model=TopPicksResponse)
async def get_top_picks():
    """Get top 5 BUY recommendations"""
    try:
        orchestrator = Orchestrator()
        results = await orchestrator.analyze_index()
        top_buys = [r for r in results if r.signal in ["STRONG_BUY", "BUY"]][:5]
        return TopPicksResponse(
            picks=[verdict_to_response(r) for r in top_buys],
            generated_at=datetime.utcnow().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/avoid-list", response_model=AvoidListResponse)
async def get_avoid_list():
    """Get stocks to avoid based on Red Team screening"""
    try:
        orchestrator = Orchestrator()
        results = await orchestrator.analyze_index()
        avoid = [r for r in results if r.signal == "AVOID"]
        return AvoidListResponse(
            stocks=[verdict_to_response(r) for r in avoid],
            generated_at=datetime.utcnow().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analyze/{symbol}", response_model=AnalysisResponse)
async def analyze_single(symbol: str):
    """Quick GET endpoint for single stock analysis"""
    try:
        orchestrator = Orchestrator()
        verdict = await orchestrator.analyze_stock(symbol.upper())
        return verdict_to_response(verdict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MCP-STYLE TOOL ENDPOINTS (for agent integration)
# ============================================================================

@app.post("/mcp/analyze_stock")
async def mcp_analyze_stock(req: AnalyzeRequest):
    """MCP-compatible tool endpoint"""
    return await analyze_stock(req)

@app.post("/mcp/analyze_index")
async def mcp_analyze_index(req: AnalyzeIndexRequest):
    """MCP-compatible tool endpoint"""
    return await analyze_index(req)

@app.post("/mcp/get_top_picks")
async def mcp_top_picks():
    """MCP-compatible tool endpoint"""
    return await get_top_picks()

@app.post("/mcp/get_avoid_list")
async def mcp_avoid_list():
    """MCP-compatible tool endpoint"""
    return await get_avoid_list()

# ============================================================================
# WEBHOOK ENDPOINTS (for Supabase integration)
# ============================================================================

@app.post("/webhook/supabase/trigger-analysis")
async def supabase_trigger(req: dict, background_tasks: BackgroundTasks):
    """Triggered by Supabase cron job or database trigger"""
    # Store results to Supabase
    return {"status": "queued", "job_id": datetime.utcnow().isoformat()}
