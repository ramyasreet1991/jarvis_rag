"""
Jarvis RAG — FastAPI Server
Real-time endpoints for querying the knowledge base and generating content.
Supports both local GPU stack (Phase 1) and cloud backends (Phase 2).
"""
import os
import json
import logging
import time
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Dict, Optional

from fastapi import FastAPI, HTTPException, Depends, Security, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

from config import CONFIG
from rag_engine import RAGEngine
from content_generator import ContentGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Request / Response Models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500,
                          description="Also accepted as 'query' for compatibility")
    query: Optional[str] = Field(default=None, description="Alias for 'question'")
    top_k: int = Field(default=5, ge=1, le=20)
    min_credibility: float = Field(default=0.65, ge=0.0, le=1.0)
    source_type: Optional[str] = Field(
        default=None,
        description="Filter by source type: youtube|podcast|blog|news|research",
    )
    date_range_days: Optional[int] = Field(
        default=None,
        description="Limit to sources published in last N days",
    )
    stream: bool = Field(default=False)

    def get_question(self) -> str:
        return self.query or self.question


class CitationResponse(BaseModel):
    title: str
    url: str
    source_type: str
    author: str = ""
    published_date: Optional[str] = None
    credibility_score: float = Field(..., ge=0.0, le=1.0)
    extract: str = ""
    relevance_score: float = 0.0


class QueryResponse(BaseModel):
    query: str
    answer: str
    citations: List[CitationResponse]
    source_count: int
    credibility_avg: float
    latency_ms: float
    has_sources: bool


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=5, max_length=500,
                       description="Also accepted as 'query' for compatibility")
    query: Optional[str] = Field(default=None, description="Alias for 'topic'")
    content_type: str = Field(
        default="youtube_shorts",
        description="youtube_shorts|blog_post|twitter_thread|newsletter|youtube_script",
    )
    tone: str = Field(default="technical",
                      description="technical|casual|professional|informative|executive")
    target_length: str = Field(default="medium",
                                description="short|medium|long")
    top_k: int = Field(default=5, ge=1, le=20)
    min_credibility: float = Field(default=0.65, ge=0.5, le=1.0)

    def get_topic(self) -> str:
        return self.query or self.topic


class GenerateResponse(BaseModel):
    query: str
    content_type: str
    title: str
    body: str
    citations: List[CitationResponse]
    source_count: int
    credibility_avg: float
    word_count: int
    estimated_duration: str
    hashtags: List[str]
    generation_time_ms: float
    generated_at: str


class IngestionRequest(BaseModel):
    """Structured ingest payload (for direct API ingestion)."""
    content_list: List[Dict] = Field(
        ...,
        description="List of content objects with title, content, url, source_type, credibility_score",
    )
    namespace: Optional[str] = Field(default=None,
                                      description="Vector store namespace (Pinecone only)")
    source_path: Optional[str] = Field(default=None,
                                        description="File/URL path for background ingestion")
    source_type: str = Field(default="rss")


class StatsResponse(BaseModel):
    total_chunks: int
    unique_sources: int
    sources: List[str]
    tier_distribution: Dict[str, int]
    avg_chunk_size: float


class HealthResponse(BaseModel):
    status: str
    rag_initialized: bool
    gpu_available: bool
    model_loaded: str
    kb_chunks: int
    uptime: str
    timestamp: str


# ── Global Singletons ─────────────────────────────────────────────────────────

rag_engine: Optional[RAGEngine] = None
generator: Optional[ContentGenerator] = None
start_time: datetime = datetime.now()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def verify_key(key: str = Security(api_key_header)):
    if key != CONFIG.API_KEY_HEADER:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return key


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag_engine, generator

    logger.info("Initializing Jarvis RAG...")

    rag_engine = RAGEngine()
    generator = ContentGenerator()

    try:
        import torch
        if torch.cuda.is_available():
            gpu_ok, gpu_name = True, torch.cuda.get_device_name(0)
        elif torch.backends.mps.is_available():
            gpu_ok, gpu_name = True, "Apple MPS (M-series)"
        else:
            gpu_ok, gpu_name = False, "CPU"
    except Exception:
        gpu_ok, gpu_name = False, "CPU"

    logger.info(f"Accelerator: {gpu_name}")
    logger.info(f"KB loaded: {rag_engine.get_stats()['total_chunks']} chunks")
    logger.info("Ready for requests")

    yield

    logger.info("Shutting down...")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Jarvis RAG API",
    description="Hybrid RAG for technology content generation — local GPU + cloud backends",
    version="2.0.0",
    lifespan=lifespan,
)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check — no auth required."""
    try:
        import torch
        gpu = torch.cuda.is_available() or torch.backends.mps.is_available()
    except Exception:
        gpu = False

    return HealthResponse(
        status="healthy" if rag_engine else "unhealthy",
        rag_initialized=rag_engine is not None,
        gpu_available=gpu,
        model_loaded=CONFIG.LOCAL_LLM_MODEL if CONFIG.USE_LOCAL_LLM else CONFIG.API_LLM_MODEL,
        kb_chunks=rag_engine.get_stats()["total_chunks"] if rag_engine else 0,
        uptime=str(datetime.now() - start_time),
        timestamp=datetime.now().isoformat(),
    )


@app.get("/stats", response_model=StatsResponse)
async def stats(_=Depends(verify_key)):
    """Knowledge base statistics."""
    if not rag_engine:
        raise HTTPException(status_code=503, detail="RAG engine not initialized")
    return StatsResponse(**rag_engine.get_stats())


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, _=Depends(verify_key)):
    """Query the knowledge base and return cited sources."""
    t0 = time.time()

    if not rag_engine:
        raise HTTPException(status_code=503, detail="RAG engine not initialized")

    question = req.get_question()

    docs = rag_engine.query(
        question,
        top_k=req.top_k,
        min_credibility=req.min_credibility,
        source_type=req.source_type,
        date_range_days=req.date_range_days,
    )

    if not docs:
        return QueryResponse(
            query=question,
            answer="I couldn't find verified information on this topic.",
            citations=[],
            source_count=0,
            credibility_avg=0.0,
            latency_ms=round((time.time() - t0) * 1000, 2),
            has_sources=False,
        )

    context = "\n\n".join(d.page_content for d in docs)
    answer = f"Based on {len(docs)} verified sources:\n\n{context[:1000]}..."

    citations = [
        CitationResponse(
            title=d.metadata.get("title", d.metadata.get("source_name", "Unknown")),
            url=d.metadata.get("url", ""),
            source_type=d.metadata.get("source_type", "unknown"),
            author=d.metadata.get("author", ""),
            published_date=d.metadata.get("published", None),
            credibility_score=d.metadata.get("credibility_score", 0.0),
            extract=d.page_content[:200],
            relevance_score=d.metadata.get("relevance_score", 0.0),
        )
        for d in docs
    ]

    avg_cred = sum(c.credibility_score for c in citations) / len(citations)

    logger.info(f"Query '{question[:60]}...' → {len(docs)} docs, {round((time.time()-t0)*1000)}ms")

    return QueryResponse(
        query=question,
        answer=answer,
        citations=citations,
        source_count=len(citations),
        credibility_avg=round(avg_cred, 3),
        latency_ms=round((time.time() - t0) * 1000, 2),
        has_sources=True,
    )


@app.post("/generate", response_model=GenerateResponse)
@app.post("/generate-content", response_model=GenerateResponse, include_in_schema=False)
async def generate(req: GenerateRequest, _=Depends(verify_key)):
    """
    Generate content from RAG context.
    POST /generate and POST /generate-content are equivalent.
    """
    t0 = time.time()

    if not rag_engine or not generator:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    topic = req.get_topic()
    docs = rag_engine.query(topic, top_k=req.top_k, min_credibility=req.min_credibility)

    if not docs:
        raise HTTPException(status_code=404, detail="No relevant content found for this topic")

    # Normalise content_type: accept both naming conventions
    content_type = req.content_type.replace("youtube_script", "youtube_shorts")

    if content_type == "youtube_shorts":
        content = generator.generate_youtube_shorts(topic, docs)
    elif content_type == "blog_post":
        content = generator.generate_blog_post(topic, docs, tone=req.tone,
                                                length=req.target_length)
    elif content_type == "twitter_thread":
        content = generator.generate_twitter_thread(topic, docs)
    elif content_type == "newsletter":
        content = generator.generate_newsletter([topic], docs)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {req.content_type}")

    generator.save_content(content)

    citations = [
        CitationResponse(
            title=s.get("name", "Unknown"),
            url=s.get("url", ""),
            source_type=s.get("source_type", "unknown"),
            author=s.get("author", ""),
            credibility_score=s.get("credibility", 0.0),
        )
        for s in content.sources
    ]

    elapsed = round((time.time() - t0) * 1000, 2)
    logger.info(f"Generated {content_type} for '{topic[:60]}' in {elapsed}ms")

    return GenerateResponse(
        query=topic,
        content_type=content.content_type,
        title=content.title,
        body=content.body,
        citations=citations,
        source_count=len(citations),
        credibility_avg=content.credibility_avg,
        word_count=content.word_count,
        estimated_duration=content.estimated_duration,
        hashtags=content.hashtags,
        generation_time_ms=elapsed,
        generated_at=content.generated_at,
    )


@app.post("/ingest")
async def ingest(
    request: IngestionRequest,
    background_tasks: BackgroundTasks,
    _=Depends(verify_key),
):
    """
    Ingest content into the knowledge base.
    Accepts either a structured content_list or a source_path for background ingestion.
    """
    if not rag_engine:
        raise HTTPException(status_code=503, detail="RAG engine not initialized")

    if request.content_list:
        async def _ingest_list():
            try:
                rag_engine.ingest_content_list(request.content_list,
                                               namespace=request.namespace)
            except Exception as e:
                logger.error(f"Ingestion error: {e}")

        background_tasks.add_task(_ingest_list)
        return {
            "status": "ingestion queued",
            "items": len(request.content_list),
            "namespace": request.namespace,
            "timestamp": datetime.now().isoformat(),
        }

    if request.source_path:
        async def _ingest_source():
            pass  # extend with source-based ingestion logic

        background_tasks.add_task(_ingest_source)
        return {
            "status": "ingestion queued",
            "source": request.source_path,
            "source_type": request.source_type,
            "timestamp": datetime.now().isoformat(),
        }

    raise HTTPException(status_code=400, detail="Provide content_list or source_path")


@app.get("/sources")
async def list_sources(
    source_type: Optional[str] = Query(None),
    min_credibility: float = Query(0.65, ge=0.0, le=1.0),
    _=Depends(verify_key),
):
    """List verified sources with optional filters."""
    from source_vetter import SourceVetter
    vetter = SourceVetter()
    sources = vetter.load_default_sources()

    filtered = [
        s.to_dict() for s in sources
        if s.credibility_score >= min_credibility
        and (source_type is None or s.source_type == source_type)
    ]

    return {
        "total": len(filtered),
        "filters": {"source_type": source_type, "min_credibility": min_credibility},
        "sources": filtered,
    }


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=CONFIG.APP_PORT,
        workers=1,   # single worker to share GPU memory
        reload=False,
        log_level="info",
    )
