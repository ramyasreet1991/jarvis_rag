"""
FastAPI Server: RAG-based Content Generation API
Endpoint for querying the knowledge base and generating cited content
"""

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
import os
import logging

from rag_system import TechContentRAG, CitedSource


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Request/Response Models
class QueryRequest(BaseModel):
    """User query request"""
    query: str = Field(..., min_length=5, max_length=500)
    num_sources: int = Field(default=5, ge=1, le=20)
    min_credibility: float = Field(default=0.65, ge=0.0, le=1.0)
    source_type: Optional[str] = Field(
        default=None,
        description="Filter by source type: youtube|podcast|blog|news|research"
    )
    date_range_days: Optional[int] = Field(
        default=None,
        description="Limit to sources published in last N days"
    )


class CitationResponse(BaseModel):
    """Citation with metadata"""
    title: str
    url: str
    source_type: str
    author: str
    published_date: Optional[str]
    credibility_score: float = Field(..., ge=0.0, le=1.0)
    extract: str
    relevance_score: float


class ContentGenerationRequest(BaseModel):
    """Request for content generation"""
    query: str = Field(..., min_length=10, max_length=1000)
    content_type: str = Field(
        default="blog_post",
        description="blog_post|twitter_thread|youtube_script|newsletter"
    )
    tone: str = Field(
        default="informative",
        description="informative|casual|technical|executive"
    )
    target_length: str = Field(
        default="medium",
        description="short|medium|long"
    )
    num_sources: int = Field(default=5, ge=1, le=10)
    min_credibility: float = Field(default=0.65, ge=0.5, le=1.0)


class ContentGenerationResponse(BaseModel):
    """Generated content with citations"""
    query: str
    content_type: str
    generated_content: str
    citations: List[CitationResponse]
    source_count: int
    generation_time_ms: float
    model: str = "gpt-4-turbo"


class QueryResponse(BaseModel):
    """Response to RAG query"""
    query: str
    response: str
    citations: List[CitationResponse]
    source_count: int
    has_sources: bool


class IngestionRequest(BaseModel):
    """Request to ingest content"""
    content_list: List[Dict]
    namespace: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    rag_initialized: bool
    timestamp: str


# Initialize FastAPI app
app = FastAPI(
    title="Tech Content RAG API",
    description="RAG system for technology content with source validation",
    version="1.0.0",
)

# Global RAG instance
rag_system: Optional[TechContentRAG] = None


@app.on_event("startup")
async def startup_event():
    """Initialize RAG system on startup"""
    global rag_system
    
    try:
        pinecone_key = os.getenv("PINECONE_API_KEY")
        pinecone_env = os.getenv("PINECONE_ENV", "us-east-1-aws")
        openai_key = os.getenv("OPENAI_API_KEY")
        
        if not all([pinecone_key, openai_key]):
            raise ValueError("Missing required environment variables")
        
        rag_system = TechContentRAG(
            pinecone_api_key=pinecone_key,
            pinecone_env=pinecone_env,
            openai_api_key=openai_key,
        )
        
        rag_system.initialize_index()
        logger.info("✅ RAG system initialized")
    
    except Exception as e:
        logger.error(f"❌ Failed to initialize RAG system: {e}")
        raise


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint
    """
    return HealthResponse(
        status="healthy" if rag_system else "unhealthy",
        rag_initialized=rag_system is not None,
        timestamp=datetime.now().isoformat(),
    )


@app.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest):
    """
    Query the RAG system and get cited sources
    
    Example:
    ```json
    {
        "query": "What are the latest developments in Kubernetes networking?",
        "num_sources": 5,
        "min_credibility": 0.7
    }
    ```
    """
    
    if not rag_system:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )
    
    try:
        result = rag_system.query(
            query_text=request.query,
            top_k=request.num_sources,
            min_credibility=request.min_credibility,
            with_citations=True,
        )
        
        citations = [
            CitationResponse(
                title=c.title,
                url=c.url,
                source_type=c.source_type,
                author=c.author,
                published_date=c.published_date,
                credibility_score=c.credibility_score,
                extract=c.extract,
                relevance_score=c.relevance_score,
            )
            for c in result['citations']
        ]
        
        return QueryResponse(
            query=request.query,
            response=result['response'],
            citations=citations,
            source_count=len(citations),
            has_sources=len(citations) > 0,
        )
    
    except Exception as e:
        logger.error(f"Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-content", response_model=ContentGenerationResponse)
async def generate_content(request: ContentGenerationRequest):
    """
    Generate content based on RAG sources
    
    Supports multiple content types:
    - blog_post: Full article (800-2000 words)
    - twitter_thread: Tweet series (5-10 tweets)
    - youtube_script: Video script with timestamps
    - newsletter: Newsletter section
    
    Example:
    ```json
    {
        "query": "How to optimize Kubernetes cluster costs",
        "content_type": "blog_post",
        "tone": "technical",
        "target_length": "long",
        "num_sources": 5,
        "min_credibility": 0.7
    }
    ```
    """
    
    if not rag_system:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )
    
    import time
    start_time = time.time()
    
    try:
        # Query RAG system
        result = rag_system.query(
            query_text=request.query,
            top_k=request.num_sources,
            min_credibility=request.min_credibility,
            with_citations=True,
        )
        
        # Prepare context for content generation
        citations = result['citations']
        context_sources = "\n".join([
            f"- {c.title}: {c.extract}"
            for c in citations
        ])
        
        # Generate content based on type and tone
        generated_content = _generate_by_type(
            query=request.query,
            content_type=request.content_type,
            tone=request.tone,
            target_length=request.target_length,
            context_sources=context_sources,
        )
        
        # Format citations
        citation_responses = [
            CitationResponse(
                title=c.title,
                url=c.url,
                source_type=c.source_type,
                author=c.author,
                published_date=c.published_date,
                credibility_score=c.credibility_score,
                extract=c.extract,
                relevance_score=c.relevance_score,
            )
            for c in citations
        ]
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        return ContentGenerationResponse(
            query=request.query,
            content_type=request.content_type,
            generated_content=generated_content,
            citations=citation_responses,
            source_count=len(citation_responses),
            generation_time_ms=elapsed_ms,
        )
    
    except Exception as e:
        logger.error(f"Content generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _generate_by_type(
    query: str,
    content_type: str,
    tone: str,
    target_length: str,
    context_sources: str,
) -> str:
    """
    Generate content based on specified type and tone
    """
    
    from llama_index.core import Settings
    
    llm = Settings.llm
    
    prompts = {
        'blog_post': f"""Write a comprehensive {target_length} blog post about: {query}

Tone: {tone}
Based on these trusted sources:
{context_sources}

Requirements:
1. Include specific citations from sources
2. Use clear section headers
3. Add practical examples and code if relevant
4. Include a conclusion with key takeaways
5. Add a "Learn More" section with source links
6. Aim for {1000 if target_length == 'long' else 600 if target_length == 'medium' else 400} words

Write the blog post:""",
        
        'twitter_thread': f"""Create an engaging Twitter thread about: {query}

Tone: {tone}
Based on these sources:
{context_sources}

Requirements:
1. Write 5-8 tweets (each under 280 characters)
2. Start with an engaging hook
3. Each tweet should build on the previous
4. Include key insights from sources
5. End with a CTA (Call To Action)
6. Format as numbered tweets (1/, 2/, etc.)

Twitter thread:""",
        
        'youtube_script': f"""Write a YouTube video script about: {query}

Tone: {tone}
Target length: {target_length} (3-5 min for short, 8-12 for medium, 15-20 for long)

Based on these sources:
{context_sources}

Requirements:
1. Include [INTRO], [MAIN], [OUTRO] sections
2. Add [CUT TO] for visual transitions
3. Include timestamps
4. Write natural, conversational language
5. Include specific points with citations
6. Add CTA at the end
7. Format clearly with speaker cues

YouTube script:""",
        
        'newsletter': f"""Write a newsletter section about: {query}

Tone: {tone}

Based on these sources:
{context_sources}

Requirements:
1. Write 150-300 words
2. Start with a hook
3. Summarize key insights from sources
4. Include 1-2 actionable takeaways
5. Include source attribution
6. Format: [HEADLINE] -> Body -> [LEARN MORE]

Newsletter section:""",
    }
    
    prompt = prompts.get(content_type, prompts['blog_post'])
    
    try:
        response = llm.complete(prompt)
        return response.text
    except Exception as e:
        logger.error(f"LLM generation error: {e}")
        return f"Error generating content: {e}"


@app.post("/ingest", response_model=Dict)
async def ingest_content(
    request: IngestionRequest,
    background_tasks: BackgroundTasks
):
    """
    Ingest content into the RAG system
    
    Example:
    ```json
    {
        "content_list": [
            {
                "title": "Article Title",
                "content": "Full article content...",
                "author": "Author Name",
                "url": "https://example.com/article",
                "source_type": "blog",
                "published_date": "2024-01-15",
                "credibility_score": 0.85,
                "tags": ["kubernetes", "devops"]
            }
        ],
        "namespace": "articles"
    }
    ```
    """
    
    if not rag_system:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )
    
    try:
        stats = rag_system.ingest_content(
            request.content_list,
            namespace=request.namespace
        )
        
        return {
            'status': 'success',
            'stats': stats,
            'timestamp': datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sources", response_model=Dict)
async def list_sources(
    source_type: Optional[str] = Query(None),
    min_credibility: float = Query(0.6, ge=0.0, le=1.0),
):
    """
    List indexed sources with filtering
    """
    
    if not rag_system:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )
    
    # Placeholder: Would query metadata index
    return {
        'total_sources': 0,
        'filters_applied': {
            'source_type': source_type,
            'min_credibility': min_credibility,
        },
        'sources': [],
    }


@app.get("/stats", response_model=Dict)
async def get_stats():
    """
    Get RAG system statistics
    """
    
    if not rag_system:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )
    
    return {
        'index_name': rag_system.index_name,
        'status': 'operational',
        'timestamp': datetime.now().isoformat(),
        # Add more stats as needed
    }


# Example startup command:
# uvicorn rag_api:app --host 0.0.0.0 --port 8000 --reload

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info",
    )
