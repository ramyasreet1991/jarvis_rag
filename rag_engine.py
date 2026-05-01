"""
Jarvis RAG — Core Engine
Chunking → Embedding → Hybrid Retrieval (Dense + BM25 + Rerank)
Optimized for RunPod RTX 4090 GPU acceleration.
"""
import os
import re
import json
import hashlib
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# GPU-aware imports
try:
    import torch
    CUDA_AVAILABLE = torch.cuda.is_available()
    DEVICE = "cuda" if CUDA_AVAILABLE else "cpu"
except ImportError:
    CUDA_AVAILABLE = False
    DEVICE = "cpu"

from config import CONFIG


@dataclass
class Chunk:
    """A processed chunk with rich metadata."""
    text: str
    chunk_index: int
    source_name: str
    source_tier: str
    source_type: str
    credibility_score: float
    published: str
    url: str
    categories: List[str]
    content_hash: str

    def to_document(self) -> Document:
        return Document(
            page_content=self.text,
            metadata={
                "source_name": self.source_name,
                "source_tier": self.source_tier,
                "source_type": self.source_type,
                "credibility_score": self.credibility_score,
                "published": self.published,
                "url": self.url,
                "categories": self.categories,
                "chunk_index": self.chunk_index,
                "content_hash": self.content_hash,
            }
        )


class Chunker:
    """Smart chunking with table/code protection."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["

", "
", ". ", " ", ""],
        )

    def protect_structured_blocks(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Replace code blocks and tables with placeholders."""
        blocks = {}

        def replacer(match):
            key = f"__BLOCK_{len(blocks)}__"
            blocks[key] = match.group(0)
            return key

        text = re.sub(r'```[\s\S]*?```', replacer, text)
        text = re.sub(r'(\|.+\|
)+', replacer, text)
        return text, blocks

    def restore_blocks(self, chunks: List[Chunk], blocks: Dict[str, str]) -> List[Chunk]:
        """Restore protected blocks into chunks."""
        for chunk in chunks:
            for key, val in blocks.items():
                chunk.text = chunk.text.replace(key, val)
        return chunks

    def chunk_content(self, content: Dict[str, Any]) -> List[Chunk]:
        """Chunk extracted content into searchable pieces."""
        text = content.get("content", "")
        if not text or len(text) < 100:
            return []

        # Protect structured blocks
        protected_text, blocks = self.protect_structured_blocks(text)

        # Split
        docs = self.splitter.create_documents([protected_text])

        # Build chunks
        chunks = []
        for i, doc in enumerate(docs):
            chunk = Chunk(
                text=doc.page_content,
                chunk_index=i,
                source_name=content.get("source_name", "unknown"),
                source_tier=content.get("source_tier", "tier_3"),
                source_type=content.get("source_type", "blog"),
                credibility_score=content.get("credibility_score", 0.65),
                published=content.get("published", datetime.now().isoformat()),
                url=content.get("url", ""),
                categories=content.get("categories", []),
                content_hash=hashlib.sha256(doc.page_content.encode()).hexdigest()[:16],
            )
            chunks.append(chunk)

        # Restore blocks
        return self.restore_blocks(chunks, blocks)

    def batch_chunk(self, contents: List[Dict[str, Any]]) -> List[Chunk]:
        """Chunk multiple contents."""
        all_chunks = []
        for content in contents:
            chunks = self.chunk_content(content)
            all_chunks.extend(chunks)
        return all_chunks


class Embedder:
    """GPU-accelerated embedding with Ollama."""

    def __init__(self):
        self.config = CONFIG.get_embed_config()
        self.provider = self.config["provider"]
        self.dimensions = self.config["dimensions"]

        if self.provider == "ollama":
            from langchain_community.embeddings import OllamaEmbeddings
            self.embedder = OllamaEmbeddings(
                model=self.config["model"],
                base_url=self.config["base_url"],
            )
        else:
            # Voyage API fallback
            from langchain_community.embeddings import VoyageAIEmbeddings
            self.embedder = VoyageAIEmbeddings(
                voyage_api_key=self.config["api_key"],
                model=self.config["model"],
            )

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Embed texts in batches (GPU-accelerated)."""
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = self.embedder.embed_documents(batch)
            all_embeddings.extend(embeddings)
            if (i + batch_size) % 128 == 0:
                print(f"   Embedded {min(i + batch_size, len(texts))}/{len(texts)}")
        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query."""
        return self.embedder.embed_query(query)


class VectorStore:
    """ChromaDB vector store with metadata filtering."""

    def __init__(self):
        self.config = CONFIG.get_vectordb_config()
        self.provider = self.config["provider"]

        if self.provider == "chromadb":
            import chromadb
            from chromadb.config import Settings

            self.client = chromadb.Client(Settings(
                anonymized_telemetry=False,
                allow_reset=True,
                persist_directory=self.config["path"],
            ))
            self.collection = self.client.get_or_create_collection(
                name=self.config["collection"],
                metadata={"hnsw:space": "cosine"}
            )
        else:
            # Qdrant fallback
            from qdrant_client import QdrantClient
            self.client = QdrantClient(
                url=self.config["url"],
                api_key=self.config["api_key"],
            )

    def upsert_chunks(self, chunks: List[Chunk], embeddings: List[List[float]]):
        """Store chunks with embeddings."""
        ids = [f"{c.content_hash}_{c.chunk_index}" for c in chunks]
        texts = [c.text for c in chunks]
        metadatas = [{
            "source_name": c.source_name,
            "source_tier": c.source_tier,
            "source_type": c.source_type,
            "credibility_score": c.credibility_score,
            "published": c.published,
            "url": c.url,
            "categories": c.categories,
            "chunk_index": c.chunk_index,
        } for c in chunks]

        self.collection.add(
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )
        print(f"   ✅ Stored {len(chunks)} chunks")

    def dense_search(self, query_embedding: List[float], 
                    top_k: int = 20,
                    min_credibility: float = 0.65) -> List[Document]:
        """Semantic search with credibility filter."""
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"credibility_score": {"$gte": min_credibility}},
        )

        docs = []
        if results["documents"] and results["documents"][0]:
            for text, meta in zip(results["documents"][0], results["metadatas"][0]):
                docs.append(Document(page_content=text, metadata=meta))
        return docs

    def get_all_chunks(self) -> List[Document]:
        """Get all stored chunks (for BM25 indexing)."""
        results = self.collection.get()
        docs = []
        if results["documents"]:
            for text, meta in zip(results["documents"], results["metadatas"]):
                docs.append(Document(page_content=text, metadata=meta))
        return docs

    def delete_by_source(self, source_name: str):
        """Remove all chunks from a source (for updates)."""
        self.collection.delete(
            where={"source_name": source_name}
        )


class HybridRetriever:
    """Dense + BM25 + Cross-Encoder Reranker (GPU-accelerated)."""

    def __init__(self, vectorstore: VectorStore, embedder: Embedder):
        self.vectorstore = vectorstore
        self.embedder = embedder

        # Build BM25 index
        all_chunks = vectorstore.get_all_chunks()
        tokenized = [c.page_content.lower().split() for c in all_chunks]

        from rank_bm25 import BM25Okapi
        self.bm25 = BM25Okapi(tokenized)
        self.all_chunks = all_chunks

        # Cross-encoder reranker (GPU if available)
        from sentence_transformers import CrossEncoder
        rerank_config = CONFIG.get_reranker_config()
        self.reranker = CrossEncoder(
            rerank_config["model"],
            device=rerank_config["device"],
        )

    def retrieve(self, query: str, 
                top_k: int = 5,
                min_credibility: float = 0.65) -> List[Document]:
        """Full hybrid retrieval pipeline."""

        # 1. Dense retrieval
        query_embed = self.embedder.embed_query(query)
        dense_docs = self.vectorstore.dense_search(
            query_embed, top_k=CONFIG.RETRIEVAL_TOP_K, 
            min_credibility=min_credibility
        )

        # 2. BM25 retrieval
        tokens = query.lower().split()
        bm25_scores = self.bm25.get_scores(tokens)
        bm25_top_idx = np.argsort(bm25_scores)[::-1][:CONFIG.RETRIEVAL_TOP_K]
        bm25_docs = [self.all_chunks[i] for i in bm25_top_idx if i < len(self.all_chunks)]

        # 3. Merge + deduplicate
        seen, merged = set(), []
        for doc in dense_docs + bm25_docs:
            h = doc.metadata.get("content_hash", doc.page_content[:50])
            if h not in seen:
                seen.add(h)
                merged.append(doc)

        # 4. Cross-encoder rerank (GPU-accelerated, ~0.5s on RTX 4090)
        if merged:
            pairs = [(query, doc.page_content) for doc in merged]
            scores = self.reranker.predict(pairs)
            ranked = sorted(zip(scores, merged), key=lambda x: x[0], reverse=True)
            return [doc for _, doc in ranked[:top_k]]

        return []


class RAGEngine:
    """End-to-end RAG: chunk → embed → store → retrieve."""

    def __init__(self):
        self.chunker = Chunker(CONFIG.CHUNK_SIZE, CONFIG.CHUNK_OVERLAP)
        self.embedder = Embedder()
        self.vectorstore = VectorStore()
        self.retriever: Optional[HybridRetriever] = None

    def ingest(self, contents: List[Dict[str, Any]]):
        """Ingest content into the knowledge base."""
        print(f"🔄 Ingesting {len(contents)} items...")

        # Chunk
        chunks = self.chunker.batch_chunk(contents)
        print(f"   📄 {len(chunks)} chunks created")

        # Embed
        texts = [c.text for c in chunks]
        embeddings = self.embedder.embed_texts(texts, batch_size=CONFIG.BATCH_SIZE)
        print(f"   🔢 {len(embeddings)} embeddings generated")

        # Store
        self.vectorstore.upsert_chunks(chunks, embeddings)

        # Rebuild retriever
        self.retriever = HybridRetriever(self.vectorstore, self.embedder)
        print("✅ Ingestion complete. Retriever rebuilt.")

    def query(self, question: str, 
             top_k: int = 5,
             min_credibility: float = 0.65) -> List[Document]:
        """Retrieve relevant chunks for a question."""
        if not self.retriever:
            self.retriever = HybridRetriever(self.vectorstore, self.embedder)

        return self.retriever.retrieve(question, top_k, min_credibility)

    def get_stats(self) -> Dict:
        """Get knowledge base statistics."""
        chunks = self.vectorstore.get_all_chunks()
        sources = set(c.metadata.get("source_name", "") for c in chunks)
        tiers = {}
        for c in chunks:
            tier = c.metadata.get("source_tier", "unknown")
            tiers[tier] = tiers.get(tier, 0) + 1

        return {
            "total_chunks": len(chunks),
            "unique_sources": len(sources),
            "sources": list(sources),
            "tier_distribution": tiers,
            "avg_chunk_size": sum(len(c.page_content) for c in chunks) / max(len(chunks), 1),
        }


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    engine = RAGEngine()

    # Test ingestion
    test_content = [{
        "title": "Test Article",
        "content": "Kubernetes is a container orchestration platform. It automates deployment, scaling, and management of containerized applications. Originally designed by Google, it is now maintained by the Cloud Native Computing Foundation.",
        "source_name": "Test Source",
        "source_tier": "tier_1",
        "source_type": "blog",
        "credibility_score": 0.95,
        "published": "2026-05-01T00:00:00",
        "url": "https://example.com/test",
        "categories": ["devops", "kubernetes"],
    }]

    engine.ingest(test_content)

    # Test query
    results = engine.query("What is Kubernetes used for?")
    for doc in results:
        print(f"
📄 Source: {doc.metadata.get('source_name')}")
        print(f"   Tier: {doc.metadata.get('source_tier')}")
        print(f"   Content: {doc.page_content[:200]}...")

    print(f"
📊 Stats: {engine.get_stats()}")
