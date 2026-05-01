"""
Jarvis RAG — Hybrid Configuration
RunPod RTX 4090 Primary | GCP Backup | Batch Processing
"""
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

@dataclass
class JarvisConfig:
    """Single source of truth. GPU-optimized for RunPod RTX 4090."""

    # === HARDWARE PROFILE ===
    GPU_AVAILABLE: bool = True           # RTX 4090 on RunPod
    GPU_VRAM_GB: int = 24
    CPU_FALLBACK: bool = False           # Only true on GCP backup

    # === PHASE CONTROL (Hybrid Toggles) ===
    USE_LOCAL_LLM: bool = True
    USE_LOCAL_EMBED: bool = True
    USE_LOCAL_VECTORDB: bool = True
    USE_LOCAL_RERANKER: bool = True

    # === LOCAL GPU STACK (Phase 1 — Zero API Cost) ===
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LOCAL_LLM_MODEL: str = "llama3.1:8b"
    LOCAL_LLM_FALLBACK: str = "mistral:7b-instruct"
    LOCAL_LLM_LIGHTWEIGHT: str = "phi3:mini"
    LOCAL_EMBED_MODEL: str = "nomic-embed-text"
    LOCAL_EMBED_DIMS: int = 768

    CHROMA_PATH: str = "/workspace/data/chroma_db"  # RunPod persistent storage
    CHROMA_COLLECTION: str = "jarvis_tech_kb"

    LOCAL_RERANK_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    LOCAL_RERANK_DEVICE: str = "cuda" if GPU_AVAILABLE else "cpu"

    # === API STACK (Phase 2 — Selective Upgrades) ===
    ANTHROPIC_API_KEY: Optional[str] = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    API_LLM_MODEL: str = "claude-haiku-4-5"
    API_LLM_MAX_TOKENS: int = 1024
    API_LLM_TEMPERATURE: float = 0.1

    VOYAGE_API_KEY: Optional[str] = field(default_factory=lambda: os.getenv("VOYAGE_API_KEY"))
    API_EMBED_MODEL: str = "voyage-3"
    API_EMBED_DIMS: int = 1024
    API_EMBED_BATCH_SIZE: int = 128

    QDRANT_URL: Optional[str] = field(default_factory=lambda: os.getenv("QDRANT_URL"))
    QDRANT_API_KEY: Optional[str] = field(default_factory=lambda: os.getenv("QDRANT_API_KEY"))
    QDRANT_COLLECTION: str = "jarvis_tech_kb"

    COHERE_API_KEY: Optional[str] = field(default_factory=lambda: os.getenv("COHERE_API_KEY"))
    API_RERANK_MODEL: str = "rerank-v3.5"

    # === RETRIEVAL TUNING ===
    RETRIEVAL_TOP_K: int = 20
    FINAL_TOP_K: int = 5
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64

    # === SOURCE VETTING ===
    CREDIBILITY_THRESHOLD: float = 0.65
    TIER_1_MIN: float = 0.90
    TIER_2_MIN: float = 0.75
    TIER_3_MIN: float = 0.65

    # === BATCH PROCESSING ===
    BATCH_SIZE: int = 32               # For embedding batches
    MAX_CONCURRENT_REQUESTS: int = 10
    CHECKPOINT_INTERVAL: int = 100       # Save progress every N items

    # === COST GUARDS ===
    DAILY_LLM_LIMIT: int = 500
    DAILY_EMBED_LIMIT: int = 2000
    DAILY_RERANK_LIMIT: int = 300

    # === PATHS (RunPod persistent volume) ===
    DOCS_PATH: str = "/workspace/docs"
    SOURCES_CONFIG_PATH: str = "/workspace/config/sources_config.json"
    BACKUP_DIR: str = "/workspace/backups"
    LOGS_DIR: str = "/workspace/logs"
    OUTPUT_DIR: str = "/workspace/output"  # Generated content

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

    def get_llm_config(self) -> Dict[str, Any]:
        if self.USE_LOCAL_LLM:
            return {
                "provider": "ollama",
                "model": self.LOCAL_LLM_MODEL,
                "base_url": self.OLLAMA_BASE_URL,
                "temperature": 0.1,
                "num_ctx": 4096,
                "device": "cuda" if self.GPU_AVAILABLE else "cpu",
            }
        return {
            "provider": "anthropic",
            "model": self.API_LLM_MODEL,
            "api_key": self.ANTHROPIC_API_KEY,
            "max_tokens": self.API_LLM_MAX_TOKENS,
            "temperature": self.API_LLM_TEMPERATURE,
        }

    def get_embed_config(self) -> Dict[str, Any]:
        if self.USE_LOCAL_EMBED:
            return {
                "provider": "ollama",
                "model": self.LOCAL_EMBED_MODEL,
                "base_url": self.OLLAMA_BASE_URL,
                "dimensions": self.LOCAL_EMBED_DIMS,
                "batch_size": self.BATCH_SIZE,
                "device": "cuda" if self.GPU_AVAILABLE else "cpu",
            }
        return {
            "provider": "voyage",
            "model": self.API_EMBED_MODEL,
            "api_key": self.VOYAGE_API_KEY,
            "dimensions": self.API_EMBED_DIMS,
            "batch_size": self.API_EMBED_BATCH_SIZE,
        }

    def get_vectordb_config(self) -> Dict[str, Any]:
        if self.USE_LOCAL_VECTORDB:
            return {
                "provider": "chromadb",
                "path": self.CHROMA_PATH,
                "collection": self.CHROMA_COLLECTION,
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
        """Determine if a component should be upgraded based on metrics."""
        thresholds = {
            "latency_ms": 10000,          # >10s avg latency
            "faithfulness": 0.80,        # <0.80 RAGAS score
            "recall": 0.75,              # <0.75 context recall
            "daily_queries": 100,        # >100 queries/day
        }
        if metric_name == "latency_ms":
            return value > thresholds[metric_name]
        return value < thresholds.get(metric_name, 0)


CONFIG = JarvisConfig()
