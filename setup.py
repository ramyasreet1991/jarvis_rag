from setuptools import setup, find_packages

setup(
    name="jarvis-rag",
    version="1.0.0",
    description="Hybrid RAG system for tech content generation",
    author="Jarvis Automation",
    packages=find_packages(),
    install_requires=[
        "python-dotenv>=1.0.1",
        "pydantic>=2.9.2",
        "langchain>=0.3.2",
        "langchain-community>=0.3.2",
        "langchain-core>=0.3.9",
        "chromadb>=0.5.7",
        "sentence-transformers>=3.0.1",
        "torch>=2.4.0",
        "rank-bm25>=0.2.2",
        "numpy>=1.26.4",
        "feedparser>=6.0.11",
        "beautifulsoup4>=4.12.3",
        "trafilatura>=1.12.2",
        "youtube-transcript-api>=0.6.2",
        "fastapi>=0.115.2",
        "uvicorn>=0.31.1",
        "httpx>=0.27.2",
        "anthropic>=0.34.2",
        "voyageai>=0.2.3",
        "cohere>=5.9.4",
        "qdrant-client>=1.11.3",
    ],
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "jarvis-rag=batch_processor:main",
        ],
    },
)
