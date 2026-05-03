"""
Jarvis RAG — Hybrid Configuration
RunPod RTX 4090 Primary (Phase 1) | Cloud APIs Backup (Phase 2)
"""
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()


def _detect_device() -> str:
    """Return 'cuda', 'mps', or 'cpu' based on available hardware."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def _default(env_key: str, fallback: str) -> str:
    return os.getenv(env_key, fallback)


@dataclass
class JarvisConfig:
    """
    Single source of truth for all backends.
    Phase 1: Local stack (zero API cost) — Ollama + ChromaDB.
              Works on Mac M2 (MPS) and RunPod RTX 4090 (CUDA).
    Phase 2: Cloud upgrades — Pinecone, OpenAI, Anthropic, Voyage, Cohere.

    All paths and device settings are overridable via environment variables,
    so the same codebase runs locally and on RunPod without changes.
    """

    # === HARDWARE PROFILE (auto-detected; override via env) ===
    DEVICE: str = field(default_factory=_detect_device)
    GPU_AVAILABLE: bool = field(default_factory=lambda: _detect_device() in ("cuda", "mps"))
    GPU_VRAM_GB: int = 24          # informational only
    CPU_FALLBACK: bool = False

    # === PHASE CONTROL (Backend Toggles) ===
    USE_LOCAL_LLM: bool = True
    USE_LOCAL_EMBED: bool = True
    USE_LOCAL_VECTORDB: bool = True
    USE_LOCAL_RERANKER: bool = True

    # === LOCAL STACK (Phase 1 — Zero API Cost) ===
    OLLAMA_BASE_URL: str = field(
        default_factory=lambda: _default("OLLAMA_BASE_URL", "http://localhost:11434"))

    # LLM — default 8b for M2, override to 32b+ in RunPod .env
    LOCAL_LLM_MODEL: str = field(
        default_factory=lambda: _default("LOCAL_LLM_MODEL", "qwen3:8b"))
    LOCAL_LLM_FALLBACK: str = field(
        default_factory=lambda: _default("LOCAL_LLM_FALLBACK", "llama3.1:8b"))
    LOCAL_LLM_LIGHTWEIGHT: str = field(
        default_factory=lambda: _default("LOCAL_LLM_LIGHTWEIGHT", "llama3.2:latest"))
    LOCAL_LLM_CTX: int = field(
        default_factory=lambda: int(_default("LOCAL_LLM_CTX", "4096")))

    # Embeddings — Ollama (default) or direct HuggingFace on CUDA (faster on GPU)
    USE_HF_EMBED: bool = field(
        default_factory=lambda: _default("USE_HF_EMBED", "false").lower() == "true")
    LOCAL_EMBED_MODEL: str = field(
        default_factory=lambda: _default("LOCAL_EMBED_MODEL", "nomic-embed-text"))
    LOCAL_EMBED_DIMS: int = field(
        default_factory=lambda: int(_default("LOCAL_EMBED_DIMS", "768")))

    CHROMA_PATH: str = field(
        default_factory=lambda: _default("CHROMA_PATH", "./data/chroma_db"))
    CHROMA_COLLECTION: str = "jarvis_tech_kb"

    # Reranker — small/fast for M2, upgrade to bge-reranker-large on RTX 4090
    LOCAL_RERANK_MODEL: str = field(
        default_factory=lambda: _default(
            "LOCAL_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"))
    LOCAL_RERANK_DEVICE: str = field(default_factory=_detect_device)

    # === CLOUD LLM (Phase 2 — Selective Upgrades) ===
    ANTHROPIC_API_KEY: Optional[str] = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    API_LLM_MODEL: str = "claude-haiku-4-5"
    API_LLM_MAX_TOKENS: int = 1024
    API_LLM_TEMPERATURE: float = 0.1

    OPENAI_API_KEY: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    OPENAI_LLM_MODEL: str = "gpt-4-turbo"
    OPENAI_LLM_TEMPERATURE: float = 0.7
    OPENAI_LLM_MAX_TOKENS: int = 2000

    # === CLOUD EMBEDDINGS (Phase 2) ===
    VOYAGE_API_KEY: Optional[str] = field(default_factory=lambda: os.getenv("VOYAGE_API_KEY"))
    API_EMBED_MODEL: str = "voyage-3"
    API_EMBED_DIMS: int = 1024
    API_EMBED_BATCH_SIZE: int = 128

    OPENAI_EMBED_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBED_DIMS: int = 1536
    OPENAI_EMBED_BATCH_SIZE: int = 20

    # === CLOUD VECTOR DBs (Phase 2) ===
    QDRANT_URL: Optional[str] = field(default_factory=lambda: os.getenv("QDRANT_URL"))
    QDRANT_API_KEY: Optional[str] = field(default_factory=lambda: os.getenv("QDRANT_API_KEY"))
    QDRANT_COLLECTION: str = "jarvis_tech_kb"

    PINECONE_API_KEY: Optional[str] = field(default_factory=lambda: os.getenv("PINECONE_API_KEY"))
    PINECONE_ENV: str = field(default_factory=lambda: os.getenv("PINECONE_ENV", "us-east-1-aws"))
    PINECONE_INDEX: str = "tech-content-rag"
    PINECONE_METRIC: str = "cosine"
    PINECONE_NAMESPACES: Dict[str, str] = field(default_factory=lambda: {
        "news": "news_articles",
        "youtube": "youtube_transcripts",
        "blog": "blog_posts",
        "podcast": "podcast_transcripts",
        "research": "research_papers",
    })

    # === CLOUD RERANKER (Phase 2) ===
    COHERE_API_KEY: Optional[str] = field(default_factory=lambda: os.getenv("COHERE_API_KEY"))
    API_RERANK_MODEL: str = "rerank-v3.5"

    # === RETRIEVAL TUNING ===
    RETRIEVAL_TOP_K: int = 20
    FINAL_TOP_K: int = 5
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    HYBRID_SEMANTIC_WEIGHT: float = 0.7
    HYBRID_BM25_WEIGHT: float = 0.3
    DATE_RANGE_DAYS: int = 90

    # === SOURCE VETTING ===
    CREDIBILITY_THRESHOLD: float = 0.65
    TIER_1_MIN: float = 0.90
    TIER_2_MIN: float = 0.75
    TIER_3_MIN: float = 0.65
    CREDIBILITY_DECAY_DAYS: int = 180

    # === BATCH PROCESSING ===
    BATCH_SIZE: int = 32
    MAX_CONCURRENT_REQUESTS: int = 10
    CHECKPOINT_INTERVAL: int = 100
    INGESTION_SCHEDULE: str = "0 2 * * *"   # 2 AM UTC daily
    INGESTION_PARALLELISM: int = 4

    # === COST GUARDS ===
    DAILY_LLM_LIMIT: int = 500
    DAILY_EMBED_LIMIT: int = 2000
    DAILY_RERANK_LIMIT: int = 300

    # === PATHS (defaults work locally; RunPod overrides via env) ===
    DOCS_PATH: str = field(
        default_factory=lambda: _default("DOCS_PATH", "./docs"))
    SOURCES_CONFIG_PATH: str = field(
        default_factory=lambda: _default("SOURCES_CONFIG_PATH", "./sources_config.json"))
    BACKUP_DIR: str = field(
        default_factory=lambda: _default("BACKUP_DIR", "./backups"))
    LOGS_DIR: str = field(
        default_factory=lambda: _default("LOGS_DIR", "./logs"))
    OUTPUT_DIR: str = field(
        default_factory=lambda: _default("OUTPUT_DIR", "./output"))

    # === API SERVER ===
    APP_PORT: int = 8000
    API_KEY_HEADER: str = field(default_factory=lambda: os.getenv("APP_API_KEY", "jarvis-local-key"))

    # === MONETIZATION TARGETS ===
    YOUTUBE_SHORTS_DAILY: int = 3
    BLOG_POSTS_WEEKLY: int = 1
    TWITTER_THREADS_WEEKLY: int = 2
    NEWSLETTERS_WEEKLY: int = 1

    # === CONTENT QUALITY ===
    MIN_RAGAS_FAITHFULNESS: float = 0.80
    MIN_RAGAS_RECALL: float = 0.75
    MIN_CONTENT_LENGTH: int = 100
    MAX_CONTENT_LENGTH: int = 50000

    # === MONITORING ===
    MONITORING_ENABLED: bool = True
    ALERT_ON_INGESTION_FAILURE: bool = True
    ALERT_ON_HIGH_LATENCY: bool = True
    ALERT_ON_LOW_PRECISION: bool = True

    # ── Backend Config Helpers ──────────────────────────────────────────────

    def get_llm_config(self) -> Dict[str, Any]:
        if self.USE_LOCAL_LLM:
            return {
                "provider": "ollama",
                "model": self.LOCAL_LLM_MODEL,
                "base_url": self.OLLAMA_BASE_URL,
                "temperature": 0.1,
                "num_ctx": self.LOCAL_LLM_CTX,
                "device": self.DEVICE,
            }
        if self.ANTHROPIC_API_KEY:
            return {
                "provider": "anthropic",
                "model": self.API_LLM_MODEL,
                "api_key": self.ANTHROPIC_API_KEY,
                "max_tokens": self.API_LLM_MAX_TOKENS,
                "temperature": self.API_LLM_TEMPERATURE,
            }
        return {
            "provider": "openai",
            "model": self.OPENAI_LLM_MODEL,
            "api_key": self.OPENAI_API_KEY,
            "max_tokens": self.OPENAI_LLM_MAX_TOKENS,
            "temperature": self.OPENAI_LLM_TEMPERATURE,
        }

    def get_embed_config(self) -> Dict[str, Any]:
        if self.USE_LOCAL_EMBED:
            if self.USE_HF_EMBED:
                # Direct HuggingFace on CUDA — bypasses Ollama HTTP overhead,
                # 5-10x faster batch embedding on RTX 4090
                return {
                    "provider": "huggingface",
                    "model": self.LOCAL_EMBED_MODEL,
                    "dimensions": self.LOCAL_EMBED_DIMS,
                    "batch_size": self.BATCH_SIZE,
                    "device": self.DEVICE,
                }
            return {
                "provider": "ollama",
                "model": self.LOCAL_EMBED_MODEL,
                "base_url": self.OLLAMA_BASE_URL,
                "dimensions": self.LOCAL_EMBED_DIMS,
                "batch_size": self.BATCH_SIZE,
                "device": self.DEVICE,
            }
        if self.VOYAGE_API_KEY:
            return {
                "provider": "voyage",
                "model": self.API_EMBED_MODEL,
                "api_key": self.VOYAGE_API_KEY,
                "dimensions": self.API_EMBED_DIMS,
                "batch_size": self.API_EMBED_BATCH_SIZE,
            }
        return {
            "provider": "openai",
            "model": self.OPENAI_EMBED_MODEL,
            "api_key": self.OPENAI_API_KEY,
            "dimensions": self.OPENAI_EMBED_DIMS,
            "batch_size": self.OPENAI_EMBED_BATCH_SIZE,
        }

    def get_vectordb_config(self) -> Dict[str, Any]:
        if self.USE_LOCAL_VECTORDB:
            return {
                "provider": "chromadb",
                "path": self.CHROMA_PATH,
                "collection": self.CHROMA_COLLECTION,
            }
        if self.PINECONE_API_KEY:
            return {
                "provider": "pinecone",
                "api_key": self.PINECONE_API_KEY,
                "environment": self.PINECONE_ENV,
                "index_name": self.PINECONE_INDEX,
                "dimension": self.OPENAI_EMBED_DIMS,
                "metric": self.PINECONE_METRIC,
                "namespaces": self.PINECONE_NAMESPACES,
            }
        return {
            "provider": "qdrant",
            "url": self.QDRANT_URL,
            "api_key": self.QDRANT_API_KEY,
            "collection": self.QDRANT_COLLECTION,
        }

    def get_reranker_config(self) -> Dict[str, Any]:
        if self.USE_LOCAL_RERANKER:
            return {
                "provider": "local",
                "model": self.LOCAL_RERANK_MODEL,
                "device": self.LOCAL_RERANK_DEVICE,
            }
        return {
            "provider": "cohere",
            "model": self.API_RERANK_MODEL,
            "api_key": self.COHERE_API_KEY,
        }

    def should_upgrade(self, metric_name: str, value: float) -> bool:
        """Return True if a component should be promoted to the cloud backend."""
        thresholds = {
            "latency_ms": 10000,
            "faithfulness": 0.80,
            "recall": 0.75,
            "daily_queries": 100,
        }
        if metric_name == "latency_ms":
            return value > thresholds[metric_name]
        return value < thresholds.get(metric_name, 0)


CONFIG = JarvisConfig()
