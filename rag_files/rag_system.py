"""
RAG System Implementation
LlamaIndex + Pinecone + OpenAI embeddings
Tracks citations and source credibility
"""

import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

from llama_index.core import (
    Document,
    VectorStoreIndex,
    SimpleDirectoryReader,
    Settings,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engines import RetrieverQueryEngine
from llama_index.core.postprocessors import SimilarityPostprocessor

import pinecone


@dataclass
class CitedSource:
    """Source citation information"""
    title: str
    url: str
    source_type: str
    author: str
    published_date: Optional[str]
    credibility_score: float
    extract: str  # Original text snippet
    relevance_score: float


class TechContentRAG:
    """
    RAG system for technology content
    Integrates source validation, embeddings, and retrieval
    """
    
    def __init__(
        self,
        pinecone_api_key: str,
        pinecone_env: str,
        openai_api_key: str,
        index_name: str = "tech-content-rag",
    ):
        self.pinecone_api_key = pinecone_api_key
        self.pinecone_env = pinecone_env
        self.index_name = index_name
        
        # Initialize Pinecone
        self._init_pinecone()
        
        # Configure LlamaIndex
        self._configure_llama_index(openai_api_key)
        
        # Initialize vector store and index
        self.vector_store = None
        self.index = None
    
    def _init_pinecone(self):
        """Initialize Pinecone connection"""
        try:
            pinecone.init(
                api_key=self.pinecone_api_key,
                environment=self.pinecone_env,
            )
            
            # Create index if doesn't exist
            if self.index_name not in pinecone.list_indexes():
                pinecone.create_index(
                    name=self.index_name,
                    dimension=1536,  # OpenAI ada-002
                    metric="cosine",
                )
            
            print(f"✅ Pinecone initialized: {self.index_name}")
        
        except Exception as e:
            print(f"❌ Error initializing Pinecone: {e}")
            raise
    
    def _configure_llama_index(self, openai_api_key: str):
        """Configure LlamaIndex settings"""
        # Set up embedding model
        embed_model = OpenAIEmbedding(
            model="text-embedding-3-small",  # More cost-effective
            api_key=openai_api_key,
        )
        
        # Set up LLM
        llm = OpenAI(
            model="gpt-4-turbo",
            api_key=openai_api_key,
            temperature=0.7,
        )
        
        # Configure global settings
        Settings.embed_model = embed_model
        Settings.llm = llm
        Settings.chunk_size = 512
        Settings.chunk_overlap = 100
    
    def initialize_index(self):
        """Initialize vector store and index"""
        try:
            # Get Pinecone index
            pinecone_index = pinecone.Index(self.index_name)
            
            # Create vector store
            self.vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
            
            # Create index
            self.index = VectorStoreIndex.from_vector_store(self.vector_store)
            
            print("✅ RAG index initialized")
        
        except Exception as e:
            print(f"❌ Error initializing index: {e}")
            raise
    
    def ingest_content(
        self,
        content_list: List[Dict],
        namespace: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Ingest extracted content into RAG system
        
        Args:
            content_list: List of dicts with keys:
                - title, content, author, url, source_type,
                - published_date, credibility_score, tags
            namespace: Pinecone namespace (optional, for organization)
        
        Returns:
            Ingestion stats
        """
        
        if not self.index:
            self.initialize_index()
        
        stats = {
            'total': len(content_list),
            'ingested': 0,
            'failed': 0,
            'duplicates': 0,
        }
        
        for content in content_list:
            try:
                # Create document with metadata
                doc = Document(
                    text=content['content'],
                    metadata={
                        'title': content.get('title', 'Unknown'),
                        'author': content.get('author', 'Unknown'),
                        'url': content.get('url', ''),
                        'source_type': content.get('source_type', 'unknown'),
                        'published_date': content.get('published_date', ''),
                        'credibility_score': content.get('credibility_score', 0.5),
                        'tags': ','.join(content.get('tags', [])),
                        'ingested_date': datetime.now().isoformat(),
                    }
                )
                
                # Add to index
                # LlamaIndex handles deduplication based on content hash
                nodes = self.index.from_documents([doc])
                
                stats['ingested'] += 1
            
            except Exception as e:
                print(f"Error ingesting {content.get('title', 'Unknown')}: {e}")
                stats['failed'] += 1
        
        print(f"✅ Ingestion complete: {stats['ingested']}/{stats['total']} documents")
        return stats
    
    def query(
        self,
        query_text: str,
        top_k: int = 5,
        min_credibility: float = 0.65,
        with_citations: bool = True,
    ) -> Dict:
        """
        Query the RAG system with source attribution
        
        Args:
            query_text: User question
            top_k: Number of top results
            min_credibility: Minimum credibility threshold
            with_citations: Include source citations
        
        Returns:
            Response with citations
        """
        
        if not self.index:
            self.initialize_index()
        
        # Create retriever with filters
        retriever = VectorIndexRetriever(
            index=self.index,
            similarity_top_k=top_k * 2,  # Get extra for filtering
        )
        
        # Retrieve nodes
        retrieved_nodes = retriever.retrieve(query_text)
        
        # Filter by credibility
        filtered_nodes = [
            node for node in retrieved_nodes
            if node.metadata.get('credibility_score', 0) >= min_credibility
        ][:top_k]
        
        # Create query engine
        query_engine = RetrieverQueryEngine(
            retriever=retriever,
            response_synthesizer_class=None,
        )
        
        # Generate response
        if filtered_nodes:
            context_text = self._build_context(filtered_nodes)
            response = self._generate_with_context(query_text, context_text)
        else:
            response = "No relevant sources found matching your criteria."
        
        # Prepare citations
        citations = [
            self._node_to_citation(node)
            for node in filtered_nodes
        ] if with_citations else []
        
        return {
            'query': query_text,
            'response': response,
            'citations': citations,
            'source_count': len(filtered_nodes),
        }
    
    def _build_context(self, nodes: List) -> str:
        """Build context string from retrieved nodes"""
        context_parts = []
        
        for i, node in enumerate(nodes, 1):
            source = node.metadata
            context_parts.append(f"""
Source {i}: {source.get('title', 'Unknown')}
Author: {source.get('author', 'Unknown')}
URL: {source.get('url', '')}
Credibility: {source.get('credibility_score', 0):.2f}

Content:
{node.get_content()[:500]}...
---""")
        
        return "\n".join(context_parts)
    
    def _generate_with_context(self, query: str, context: str) -> str:
        """Generate response using context"""
        from llama_index.llms.openai import OpenAI
        
        llm = Settings.llm
        
        prompt = f"""You are a technical content expert. 
        
Using ONLY the provided sources below, answer this question: {query}

SOURCES:
{context}

Requirements:
1. Base your response entirely on the provided sources
2. Include specific citations (e.g., "According to [Source 1]...")
3. If sources conflict, mention both perspectives
4. Note if information is recent or potentially outdated
5. Don't make up information not in sources

Answer:"""
        
        response = llm.complete(prompt)
        return response.text
    
    def _node_to_citation(self, node) -> CitedSource:
        """Convert retrieved node to citation"""
        metadata = node.metadata
        
        return CitedSource(
            title=metadata.get('title', 'Unknown'),
            url=metadata.get('url', ''),
            source_type=metadata.get('source_type', 'unknown'),
            author=metadata.get('author', 'Unknown'),
            published_date=metadata.get('published_date'),
            credibility_score=metadata.get('credibility_score', 0.5),
            extract=node.get_content()[:300],
            relevance_score=node.score or 0.0,
        )
    
    def bulk_ingest_from_feeds(
        self,
        feed_configs: List[Dict],
        source_validator,
    ):
        """
        Bulk ingest from multiple feeds with validation
        
        Args:
            feed_configs: List of feed configurations
            source_validator: SourceValidator instance
        """
        
        from content_extraction import MultiSourceExtractor
        
        extractor = MultiSourceExtractor()
        all_content = []
        
        for config in feed_configs:
            feed_url = config['url']
            source_type = config['type']
            
            print(f"Processing {source_type}: {feed_url}")
            
            try:
                if source_type == 'rss':
                    contents = extractor.rss.extract_feed(feed_url)
                elif source_type == 'youtube':
                    content = extractor.youtube.extract(feed_url)
                    contents = [content] if content else []
                elif source_type == 'podcast':
                    content = extractor.podcast.extract(feed_url)
                    contents = [content] if content else []
                else:
                    content = extractor.blog.extract(feed_url)
                    contents = [content] if content else []
                
                # Validate and score sources
                for content in contents:
                    if content:
                        all_content.append({
                            'title': content.title,
                            'content': content.content,
                            'author': content.author,
                            'url': content.url,
                            'source_type': content.source_type,
                            'published_date': content.published_date.isoformat() if content.published_date else None,
                            'credibility_score': config.get('credibility_score', 0.75),
                            'tags': content.tags,
                        })
            
            except Exception as e:
                print(f"Error processing {feed_url}: {e}")
        
        # Ingest all content
        stats = self.ingest_content(all_content)
        return stats
    
    def hybrid_search(
        self,
        query_text: str,
        top_k: int = 5,
    ) -> List[Dict]:
        """
        Hybrid search: semantic + BM25 text search
        (Pinecone Pro feature)
        """
        # Placeholder for hybrid search implementation
        # Requires Pinecone hybrid search plugin
        
        # For now, use semantic search
        return self.query(query_text, top_k=top_k)['citations']


# Example usage and initialization
if __name__ == "__main__":
    import os
    
    # Configure with environment variables
    pinecone_key = os.getenv("PINECONE_API_KEY")
    pinecone_env = os.getenv("PINECONE_ENV", "us-east-1-aws")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    # Initialize RAG system
    rag = TechContentRAG(
        pinecone_api_key=pinecone_key,
        pinecone_env=pinecone_env,
        openai_api_key=openai_key,
    )
    
    # Initialize index
    rag.initialize_index()
    
    # Example: Ingest sample content
    sample_content = [
        {
            'title': 'Kubernetes Best Practices',
            'content': 'Kubernetes (K8s) is an open-source container orchestration...',
            'author': 'Cloud Native Computing Foundation',
            'url': 'https://kubernetes.io/docs/',
            'source_type': 'documentation',
            'published_date': '2024-01-01',
            'credibility_score': 1.0,
            'tags': ['kubernetes', 'devops', 'containers'],
        }
    ]
    
    # Ingest
    # stats = rag.ingest_content(sample_content)
    # print(f"Ingested: {stats}")
    
    # Query
    # result = rag.query("What are Kubernetes best practices?")
    # print(f"\nResponse: {result['response']}")
    # print(f"\nCitations:")
    # for citation in result['citations']:
    #     print(f"  - {citation.title} ({citation.credibility_score:.2f})")
