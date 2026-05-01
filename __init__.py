"""
Jarvis RAG — Hybrid Tech Content Engine
Zero-cost local RAG with selective API upgrades.
Optimized for RunPod RTX 4090 + GCP backup.
"""

__version__ = "1.0.0"
__author__ = "Jarvis Automation"

from .config import CONFIG, JarvisConfig
from .source_vetter import SourceVetter, Source, TrustTier
from .content_extractor import ContentExtractor, ExtractedContent
from .rag_engine import RAGEngine, Chunker, Embedder, VectorStore, HybridRetriever
from .content_generator import ContentGenerator, GeneratedContent
from .batch_processor import BatchProcessor, BatchReport

__all__ = [
    "CONFIG",
    "JarvisConfig",
    "SourceVetter",
    "Source",
    "TrustTier",
    "ContentExtractor",
    "ExtractedContent",
    "RAGEngine",
    "Chunker",
    "Embedder",
    "VectorStore",
    "HybridRetriever",
    "ContentGenerator",
    "GeneratedContent",
    "BatchProcessor",
    "BatchReport",
]
