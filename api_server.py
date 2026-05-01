"""
Jarvis RAG — FastAPI Server
Real-time endpoints for querying KB and generating content.
Runs on RunPod RTX 4090 with GPU-accelerated inference.
"""
import os
import json
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Dict, Optional

from fastapi import FastAPI, HTTPException, Depends, Security, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

from config import CONFIG
from rag_engine import RAGEngine
from content_generator import ContentGenerator


# ── Request/Response Models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    min_credibility: float = Field(default=0.65, ge=0, le=1)
    stream: bool = Field(default=False)

class QueryResponse(BaseModel):
    answer: str
    sources: List[Dict]
    credibility_avg: float
    latency_ms: float
    chunks_used: int

class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=5, max_length=200)
    content_type: str = Field(default="youtube_shorts", 
                               pattern="^(youtube_shorts|blog_post|twitter_thread|newsletter)$")
    tone: str = Field(default="technical", pattern="^(technical|casual|professional)$")
    top_k: int = Field(default=5, ge=1, le=20)

class GenerateResponse(BaseModel):
    content_type: str
    title: str
    body: str
    sources: List[Dict]
    credibility_avg: float
    word_count: int
    estimated_duration: str
    hashtags: List[str]
    generated_at: str

class StatsResponse(BaseModel):
    total_chunks: int
    unique_sources: int
    sources: List[str]
    tier_distribution: Dict[str, int]
    avg_chunk_size: float

class HealthResponse(BaseModel):
    status: str
    gpu_available: bool
    model_loaded: str
    kb_chunks: int
    uptime: str


# ── Global Components ────────────────────────────────────────────────────────

rag_engine: Optional[RAGEngine] = None
generator: Optional[ContentGenerator] = None
start_time: datetime = datetime.now()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def verify_key(key: str = Security(api_key_header)):
    if key != CONFIG.API_KEY_HEADER:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return key


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag_engine, generator

    print("🚀 Initializing Jarvis RAG...")

    # Load RAG engine
    rag_engine = RAGEngine()

    # Load generator
    generator = ContentGenerator()

    # Check GPU
    try:
        import torch
        gpu_available = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if gpu_available else "None"
    except:
        gpu_available = False
        gpu_name = "None"

    print(f"   ✅ GPU: {gpu_name}" if gpu_available else "   ⚠️ Running on CPU")
    print(f"   ✅ KB loaded: {rag_engine.get_stats()['total_chunks']} chunks")
    print(f"   ✅ Ready for requests")

    yield

    print("🛑 Shutting down...")


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Jarvis RAG API",
    description="Zero-cost hybrid RAG for tech content generation",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    import torch
    gpu = torch.cuda.is_available() if hasattr(torch, 'cuda') else False

    return HealthResponse(
        status="healthy",
        gpu_available=gpu,
        model_loaded=CONFIG.LOCAL_LLM_MODEL,
        kb_chunks=rag_engine.get_stats()["total_chunks"] if rag_engine else 0,
        uptime=str(datetime.now() - start_time),
    )

@app.get("/stats", response_model=StatsResponse)
async def stats(_=Depends(verify_key)):
    """Get knowledge base statistics."""
    if not rag_engine:
        raise HTTPException(status_code=503, detail="RAG engine not initialized")

    stats = rag_engine.get_stats()
    return StatsResponse(**stats)

@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, _=Depends(verify_key)):
    """Query the knowledge base."""
    import time
    start = time.time()

    if not rag_engine:
        raise HTTPException(status_code=503, detail="RAG engine not initialized")

    docs = rag_engine.query(
        req.question,
        top_k=req.top_k,
        min_credibility=req.min_credibility,
    )

    if not docs:
        return QueryResponse(
            answer="I couldn't find verified information on this topic.",
            sources=[],
            credibility_avg=0,
            latency_ms=round((time.time() - start) * 1000, 2),
            chunks_used=0,
        )

    # Build answer from context
    context = "

".join([d.page_content for d in docs])

    # Simple answer generation (can be enhanced)
    answer = f"Based on {len(docs)} verified sources:

{context[:1000]}..."

    sources = [{
        "name": d.metadata.get("source_name", "Unknown"),
        "tier": d.metadata.get("source_tier", "unknown"),
        "credibility": d.metadata.get("credibility_score", 0),
        "url": d.metadata.get("url", ""),
    } for d in docs]

    avg_cred = sum(s["credibility"] for s in sources) / len(sources) if sources else 0

    return QueryResponse(
        answer=answer,
        sources=sources,
        credibility_avg=round(avg_cred, 3),
        latency_ms=round((time.time() - start) * 1000, 2),
        chunks_used=len(docs),
    )

@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, _=Depends(verify_key)):
    """Generate content from RAG context."""
    import time
    start = time.time()

    if not rag_engine or not generator:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    # Retrieve context
    docs = rag_engine.query(req.topic, top_k=req.top_k, min_credibility=0.65)

    if not docs:
        raise HTTPException(status_code=404, detail="No relevant content found")

    # Generate based on type
    if req.content_type == "youtube_shorts":
        content = generator.generate_youtube_shorts(req.topic, docs)
    elif req.content_type == "blog_post":
        content = generator.generate_blog_post(req.topic, docs, tone=req.tone)
    elif req.content_type == "twitter_thread":
        content = generator.generate_twitter_thread(req.topic, docs)
    elif req.content_type == "newsletter":
        content = generator.generate_newsletter([req.topic], docs)
    else:
        raise HTTPException(status_code=400, detail="Invalid content type")

    # Save
    generator.save_content(content)

    return GenerateResponse(
        content_type=content.content_type,
        title=content.title,
        body=content.body,
        sources=content.sources,
        credibility_avg=content.credibility_avg,
        word_count=content.word_count,
        estimated_duration=content.estimated_duration,
        hashtags=content.hashtags,
        generated_at=content.generated_at,
    )

@app.post("/ingest")
async def ingest(background_tasks: BackgroundTasks, 
                source_path: str, 
                source_type: str = "rss",
                _=Depends(verify_key)):
    """Trigger background ingestion of a source."""
    async def _ingest():
        # Implementation would fetch and ingest
        pass

    background_tasks.add_task(_ingest)
    return {"status": "ingestion queued", "source": source_path}

@app.get("/sources")
async def list_sources(_=Depends(verify_key)):
    """List all verified sources."""
    from source_vetter import SourceVetter
    vetter = SourceVetter()
    sources = vetter.load_default_sources()
    return {
        "total": len(sources),
        "sources": [s.to_dict() for s in sources],
    }


# ── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=CONFIG.APP_PORT,
        workers=1,  # Single worker for GPU sharing
        reload=False,
    )
