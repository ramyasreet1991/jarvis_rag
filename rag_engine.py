"""
Jarvis RAG — Core Engine
Chunking → Embedding → Hybrid Retrieval (Dense + BM25 + Cross-Encoder Rerank)
Works on CUDA (RunPod RTX 4090), MPS (Mac M2), and CPU.
"""
import re
import json
import hashlib
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

try:
    import torch
    if torch.cuda.is_available():
        DEVICE = "cuda"
    elif torch.backends.mps.is_available():
        DEVICE = "mps"
    else:
        DEVICE = "cpu"
except ImportError:
    DEVICE = "cpu"

from config import CONFIG


@dataclass
class Chunk:
    """A processed text chunk with rich metadata."""
    text: str
    title: str
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
                "title": self.title,
                "source_name": self.source_name,
                "source_tier": self.source_tier,
                "source_type": self.source_type,
                "credibility_score": self.credibility_score,
                "published": self.published,
                "url": self.url,
                "categories": self.categories,
                "chunk_index": self.chunk_index,
                "content_hash": self.content_hash,
            },
        )


class Chunker:
    """Smart chunking with code/table block protection."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def _protect_blocks(self, text: str) -> Tuple[str, Dict[str, str]]:
        blocks: Dict[str, str] = {}

        def replacer(match):
            key = f"__BLOCK_{len(blocks)}__"
            blocks[key] = match.group(0)
            return key

        text = re.sub(r"```[\s\S]*?```", replacer, text)
        text = re.sub(r"(\|.+\|\n)+", replacer, text)
        return text, blocks

    def _restore_blocks(self, chunks: List["Chunk"], blocks: Dict[str, str]) -> List["Chunk"]:
        for chunk in chunks:
            for key, val in blocks.items():
                chunk.text = chunk.text.replace(key, val)
        return chunks

    def chunk_content(self, content: Dict[str, Any]) -> List[Chunk]:
        text = content.get("content", "")
        if not text or len(text) < 100:
            return []

        protected, blocks = self._protect_blocks(text)
        docs = self.splitter.create_documents([protected])

        chunks = [
            Chunk(
                text=doc.page_content,
                title=content.get("title", content.get("source_name", "unknown")),
                chunk_index=i,
                source_name=content.get("source_name", "unknown"),
                source_tier=content.get("source_tier", "tier_3"),
                source_type=content.get("source_type", "blog"),
                credibility_score=float(content.get("credibility_score", 0.65)),
                published=content.get("published", datetime.now().isoformat()),
                url=content.get("url", ""),
                categories=content.get("categories", content.get("tags", [])),
                content_hash=hashlib.sha256(doc.page_content.encode()).hexdigest()[:16],
            )
            for i, doc in enumerate(docs)
        ]
        return self._restore_blocks(chunks, blocks)

    def batch_chunk(self, contents: List[Dict[str, Any]]) -> List[Chunk]:
        all_chunks: List[Chunk] = []
        for content in contents:
            all_chunks.extend(self.chunk_content(content))
        return all_chunks


class Embedder:
    """Embedding via HuggingFace CUDA (GPU), Ollama (local), or cloud APIs."""

    def __init__(self):
        self.config = CONFIG.get_embed_config()
        provider = self.config["provider"]

        if provider == "huggingface":
            # Direct CUDA inference — bypasses Ollama HTTP, 5-10x faster on GPU
            # Recommended for RTX 4090: BAAI/bge-large-en-v1.5 (1024-dim, MTEB top-10)
            from langchain_community.embeddings import HuggingFaceEmbeddings
            self.embedder = HuggingFaceEmbeddings(
                model_name=self.config["model"],
                model_kwargs={"device": self.config["device"]},
                encode_kwargs={
                    "batch_size": self.config["batch_size"],
                    "normalize_embeddings": True,
                },
            )
        elif provider == "ollama":
            from langchain_ollama import OllamaEmbeddings
            self.embedder = OllamaEmbeddings(
                model=self.config["model"],
                base_url=self.config["base_url"],
            )
        elif provider == "voyage":
            from langchain_community.embeddings import VoyageAIEmbeddings
            self.embedder = VoyageAIEmbeddings(
                voyage_api_key=self.config["api_key"],
                model=self.config["model"],
            )
        else:
            from langchain_community.embeddings import OpenAIEmbeddings
            self.embedder = OpenAIEmbeddings(
                openai_api_key=self.config["api_key"],
                model=self.config["model"],
            )

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            all_embeddings.extend(self.embedder.embed_documents(batch))
        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        return self.embedder.embed_query(query)


class VectorStore:
    """ChromaDB or Qdrant (embedded) or Pinecone (cloud) vector store."""

    COLLECTION = "jarvis_rag"

    def __init__(self):
        self.config = CONFIG.get_vectordb_config()
        provider = self.config["provider"]

        if provider == "chromadb":
            import chromadb
            path = self.config["path"]
            Path(path).mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(path=path)
            self.collection = self.client.get_or_create_collection(
                name=self.config["collection"],
                metadata={"hnsw:space": "cosine"},
            )
            self._provider = "chromadb"

        elif provider == "qdrant":
            from qdrant_client import QdrantClient
            from qdrant_client.models import (
                Distance, VectorParams, PointStruct,
                PayloadSchemaType,
            )
            # Embedded mode: path= writes to disk; no separate server needed
            path = self.config.get("path", "/workspace/data/qdrant_db")
            url  = self.config.get("url")
            if url:
                # Cloud / remote Qdrant
                self.client = QdrantClient(url=url, api_key=self.config.get("api_key"))
            else:
                # Local embedded — persists to /workspace
                Path(path).mkdir(parents=True, exist_ok=True)
                self.client = QdrantClient(path=path)

            dims = CONFIG.LOCAL_EMBED_DIMS
            # Create collection if it doesn't exist yet
            existing = [c.name for c in self.client.get_collections().collections]
            if self.COLLECTION not in existing:
                self.client.create_collection(
                    collection_name=self.COLLECTION,
                    vectors_config=VectorParams(size=dims, distance=Distance.COSINE),
                )
                # Index payload fields for fast filtering
                for field, schema in [
                    ("credibility_score", PayloadSchemaType.FLOAT),
                    ("source_type",       PayloadSchemaType.KEYWORD),
                    ("source_tier",       PayloadSchemaType.KEYWORD),
                    ("published",         PayloadSchemaType.KEYWORD),
                ]:
                    self.client.create_payload_index(
                        collection_name=self.COLLECTION,
                        field_name=field,
                        field_schema=schema,
                    )
            self._provider = "qdrant"

        elif provider == "pinecone":
            from pinecone import Pinecone
            pc = Pinecone(api_key=self.config["api_key"])
            index_name = self.config["index_name"]
            if index_name not in [idx.name for idx in pc.list_indexes()]:
                pc.create_index(
                    name=index_name,
                    dimension=self.config["dimension"],
                    metric=self.config["metric"],
                )
            self.index = pc.Index(index_name)
            self._provider = "pinecone"

        else:
            raise ValueError(f"Unknown vector DB provider: {provider}")

    # ── Upsert ────────────────────────────────────────────────────────────────

    def upsert_chunks(self, chunks: List[Chunk], embeddings: List[List[float]]):
        if self._provider == "chromadb":
            self.collection.add(
                embeddings=embeddings,
                documents=[c.text for c in chunks],
                metadatas=[{
                    "title": c.title,
                    "source_name": c.source_name,
                    "source_tier": c.source_tier,
                    "source_type": c.source_type,
                    "credibility_score": c.credibility_score,
                    "published": c.published,
                    "url": c.url,
                    "chunk_index": c.chunk_index,
                    "content_hash": c.content_hash,
                    "categories": json.dumps(c.categories),
                } for c in chunks],
                ids=[f"{c.content_hash}_{c.chunk_index}" for c in chunks],
            )

        elif self._provider == "qdrant":
            from qdrant_client.models import PointStruct
            points = [
                PointStruct(
                    id=abs(hash(f"{c.content_hash}_{c.chunk_index}")) % (2**63),
                    vector=emb,
                    payload={
                        "text": c.text,
                        "title": c.title,
                        "source_name": c.source_name,
                        "source_tier": c.source_tier,
                        "source_type": c.source_type,
                        "credibility_score": c.credibility_score,
                        "published": c.published,
                        "url": c.url,
                        "chunk_index": c.chunk_index,
                        "content_hash": c.content_hash,
                        "categories": c.categories,
                    },
                )
                for c, emb in zip(chunks, embeddings)
            ]
            self.client.upsert(collection_name=self.COLLECTION, points=points)

    # ── Dense search ──────────────────────────────────────────────────────────

    def dense_search(
        self,
        query_embedding: List[float],
        top_k: int = 20,
        min_credibility: float = 0.65,
        source_type: Optional[str] = None,
        date_range_days: Optional[int] = None,
    ) -> List[Document]:

        if self._provider == "chromadb":
            where: Dict[str, Any] = {"credibility_score": {"$gte": min_credibility}}
            if source_type:
                where["source_type"] = {"$eq": source_type}
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, self.collection.count() or 1),
                where=where,
            )
            docs = []
            if results["documents"] and results["documents"][0]:
                cutoff = None
                if date_range_days:
                    cutoff = (datetime.now() - timedelta(days=date_range_days)).isoformat()
                for text, meta in zip(results["documents"][0], results["metadatas"][0]):
                    if cutoff and meta.get("published", "") < cutoff:
                        continue
                    if "categories" in meta and isinstance(meta["categories"], str):
                        meta["categories"] = json.loads(meta["categories"])
                    docs.append(Document(page_content=text, metadata=meta))
            return docs

        elif self._provider == "qdrant":
            from qdrant_client.models import Filter, FieldCondition, Range, MatchValue

            must = [FieldCondition(key="credibility_score",
                                   range=Range(gte=min_credibility))]
            if source_type:
                must.append(FieldCondition(key="source_type",
                                           match=MatchValue(value=source_type)))
            if date_range_days:
                cutoff = (datetime.now() - timedelta(days=date_range_days)).isoformat()
                must.append(FieldCondition(key="published",
                                           range=Range(gte=cutoff)))

            results = self.client.search(
                collection_name=self.COLLECTION,
                query_vector=query_embedding,
                query_filter=Filter(must=must) if must else None,
                limit=top_k,
                with_payload=True,
            )
            return [
                Document(
                    page_content=r.payload.get("text", ""),
                    metadata={k: v for k, v in r.payload.items() if k != "text"},
                )
                for r in results
            ]

        return []

    # ── Bulk fetch (for BM25 + stats) ─────────────────────────────────────────

    def get_all_chunks(self) -> List[Document]:
        if self._provider == "chromadb":
            count = self.collection.count()
            if count == 0:
                return []
            results = self.collection.get()
            docs = []
            for text, meta in zip(results["documents"], results["metadatas"]):
                if "categories" in meta and isinstance(meta["categories"], str):
                    meta["categories"] = json.loads(meta["categories"])
                docs.append(Document(page_content=text, metadata=meta))
            return docs

        elif self._provider == "qdrant":
            total = self.client.get_collection(self.COLLECTION).points_count
            if not total:
                return []
            docs, offset = [], None
            while True:
                batch, next_offset = self.client.scroll(
                    collection_name=self.COLLECTION,
                    limit=500,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for pt in batch:
                    docs.append(Document(
                        page_content=pt.payload.get("text", ""),
                        metadata={k: v for k, v in pt.payload.items() if k != "text"},
                    ))
                if next_offset is None:
                    break
                offset = next_offset
            return docs

        return []

    # ── Count / delete ────────────────────────────────────────────────────────

    def count(self) -> int:
        if self._provider == "chromadb":
            return self.collection.count()
        elif self._provider == "qdrant":
            return self.client.get_collection(self.COLLECTION).points_count or 0
        return 0

    def delete_by_source(self, source_name: str):
        if self._provider == "chromadb":
            self.collection.delete(where={"source_name": source_name})
        elif self._provider == "qdrant":
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            self.client.delete(
                collection_name=self.COLLECTION,
                points_selector=Filter(must=[
                    FieldCondition(key="source_name",
                                   match=MatchValue(value=source_name))
                ]),
            )


class HybridRetriever:
    """Dense + BM25 + Cross-Encoder reranker. Works on CUDA, MPS, and CPU."""

    def __init__(self, vectorstore: VectorStore, embedder: Embedder):
        self.vectorstore = vectorstore
        self.embedder = embedder

        all_chunks = vectorstore.get_all_chunks()
        tokenized = [c.page_content.lower().split() for c in all_chunks]

        from rank_bm25 import BM25Okapi
        self.bm25 = BM25Okapi(tokenized) if tokenized else None
        self.all_chunks = all_chunks

        from sentence_transformers import CrossEncoder
        rerank_cfg = CONFIG.get_reranker_config()
        device = rerank_cfg["device"]
        # sentence-transformers does not support 'mps' string on older versions; fall back to cpu
        if device == "mps":
            try:
                self.reranker = CrossEncoder(rerank_cfg["model"], device="mps")
            except Exception:
                self.reranker = CrossEncoder(rerank_cfg["model"], device="cpu")
        else:
            self.reranker = CrossEncoder(rerank_cfg["model"], device=device)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_credibility: float = 0.65,
        source_type: Optional[str] = None,
        date_range_days: Optional[int] = None,
    ) -> List[Document]:
        # 1. Dense retrieval
        query_embed = self.embedder.embed_query(query)
        dense_docs = self.vectorstore.dense_search(
            query_embed,
            top_k=CONFIG.RETRIEVAL_TOP_K,
            min_credibility=min_credibility,
            source_type=source_type,
            date_range_days=date_range_days,
        )

        # 2. BM25 retrieval
        bm25_docs: List[Document] = []
        if self.bm25 and self.all_chunks:
            tokens = query.lower().split()
            scores = self.bm25.get_scores(tokens)
            top_idx = np.argsort(scores)[::-1][: CONFIG.RETRIEVAL_TOP_K]
            bm25_docs = [self.all_chunks[i] for i in top_idx if i < len(self.all_chunks)]

        # 3. Merge + deduplicate
        seen: set = set()
        merged: List[Document] = []
        for doc in dense_docs + bm25_docs:
            key = doc.metadata.get("content_hash", doc.page_content[:50])
            if key not in seen:
                seen.add(key)
                merged.append(doc)

        if not merged:
            return []

        # 4. Cross-encoder rerank
        pairs = [(query, doc.page_content) for doc in merged]
        rerank_scores = self.reranker.predict(pairs)
        ranked = sorted(zip(rerank_scores, merged), key=lambda x: x[0], reverse=True)
        return [doc for _, doc in ranked[:top_k]]


class RAGEngine:
    """End-to-end pipeline: ingest → embed → store → retrieve."""

    def __init__(self):
        self.chunker = Chunker(CONFIG.CHUNK_SIZE, CONFIG.CHUNK_OVERLAP)
        self.embedder = Embedder()
        self.vectorstore = VectorStore()
        self._retriever: Optional[HybridRetriever] = None

    def _get_retriever(self) -> HybridRetriever:
        if self._retriever is None:
            self._retriever = HybridRetriever(self.vectorstore, self.embedder)
        return self._retriever

    def ingest(self, contents: List[Dict[str, Any]]):
        """Chunk, embed, and store a list of content dicts."""
        print(f"Ingesting {len(contents)} items...")
        chunks = self.chunker.batch_chunk(contents)
        print(f"  {len(chunks)} chunks created")

        if not chunks:
            return

        texts = [c.text for c in chunks]
        embeddings = self.embedder.embed_texts(texts, batch_size=CONFIG.BATCH_SIZE)
        self.vectorstore.upsert_chunks(chunks, embeddings)

        # Invalidate retriever so it's rebuilt with new data
        self._retriever = None
        print(f"  Ingestion complete. Total chunks: {self.vectorstore.count()}")

    def ingest_content_list(
        self,
        content_list: List[Dict],
        namespace: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Ingest a structured list from the API /ingest endpoint.
        Returns stats dict with ingested/failed counts.
        """
        ingested, failed = 0, 0
        for item in content_list:
            try:
                self.ingest([item])
                ingested += 1
            except Exception as e:
                print(f"  Failed to ingest '{item.get('title', '?')}': {e}")
                failed += 1
        return {"ingested": ingested, "failed": failed}

    def query(
        self,
        question: str,
        top_k: int = 5,
        min_credibility: float = 0.65,
        source_type: Optional[str] = None,
        date_range_days: Optional[int] = None,
    ) -> List[Document]:
        """Retrieve the most relevant chunks for a question."""
        if self.vectorstore.count() == 0:
            return []
        return self._get_retriever().retrieve(
            question,
            top_k=top_k,
            min_credibility=min_credibility,
            source_type=source_type,
            date_range_days=date_range_days,
        )

    def get_stats(self) -> Dict:
        chunks = self.vectorstore.get_all_chunks()
        sources = {c.metadata.get("source_name", "") for c in chunks}
        tiers: Dict[str, int] = {}
        for c in chunks:
            t = c.metadata.get("source_tier", "unknown")
            tiers[t] = tiers.get(t, 0) + 1

        return {
            "total_chunks": len(chunks),
            "unique_sources": len(sources),
            "sources": sorted(sources),
            "tier_distribution": tiers,
            "avg_chunk_size": (
                sum(len(c.page_content) for c in chunks) / max(len(chunks), 1)
            ),
        }


# ── Quick test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    engine = RAGEngine()

    test_content = [{
        "title": "Kubernetes Basics",
        "content": (
            "Kubernetes is a container orchestration platform. "
            "It automates deployment, scaling, and management of containerized applications. "
            "Originally designed by Google, it is now maintained by the Cloud Native Computing Foundation."
        ),
        "source_name": "Test Source",
        "source_tier": "tier_1",
        "source_type": "blog",
        "credibility_score": 0.95,
        "published": "2026-05-01T00:00:00",
        "url": "https://example.com/test",
        "categories": ["devops", "kubernetes"],
    }]

    engine.ingest(test_content)

    results = engine.query("What is Kubernetes used for?")
    for doc in results:
        print(f"\nSource: {doc.metadata.get('source_name')}")
        print(f"Content: {doc.page_content[:200]}")

    print(f"\nStats: {engine.get_stats()}")
