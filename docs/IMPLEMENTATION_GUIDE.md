# Technology Content RAG System - Implementation Guide

## Quick Start (Week 1)

### 1. Environment Setup

```bash
# Clone/create project directory
mkdir tech-content-rag && cd tech-content-rag

# Create Python virtual environment
python3.11 -m venv venv
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create `.env` file:

```env
# Pinecone Configuration
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_ENV=us-east-1-aws
PINECONE_INDEX_NAME=tech-content-rag

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4-turbo

# YouTube API (optional, for full metadata)
YOUTUBE_API_KEY=your-youtube-api-key

# Postgres Configuration (for metadata)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=rag_user
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=tech_content_rag

# Airflow Configuration
AIRFLOW_HOME=./airflow
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://rag_user:secure_password@localhost:5432/tech_content_rag

# API Configuration
API_PORT=8000
API_HOST=0.0.0.0
LOG_LEVEL=INFO
```

### 3. Install System Dependencies

```bash
# For macOS
brew install postgresql redis

# For Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib redis-server

# Start services
brew services start postgresql  # macOS
# or: systemctl start postgresql  # Linux
```

### 4. Initialize Database

```bash
# Create PostgreSQL database
createdb tech_content_rag

# Run schema
psql tech_content_rag < schema.sql
```

---

## Phase 1: Source Validation (Week 1)

### Step 1.1: Define Trusted Sources

Create `sources_config.json`:

```json
{
  "sources": [
    {
      "url": "https://news.ycombinator.com/",
      "type": "news",
      "domain": "news.ycombinator.com",
      "author": "YCombinator",
      "name": "Hacker News",
      "subscribers": 500000,
      "credibility_score": 1.0
    },
    {
      "url": "https://www.youtube.com/@ThePrimeagen/videos",
      "type": "youtube",
      "domain": "youtube.com",
      "author": "ThePrimeagen",
      "name": "ThePrimeagen",
      "subscribers": 250000,
      "credibility_score": 0.95
    },
    {
      "url": "https://feeds.infoq.com/news",
      "type": "rss",
      "domain": "infoq.com",
      "author": "InfoQ",
      "name": "InfoQ News Feed",
      "subscribers": 100000,
      "credibility_score": 0.90
    }
  ]
}
```

### Step 1.2: Test Source Validation

```bash
python3 -c "
from source_validation import SourceValidator, SourceMetadata, SourceType
import json

validator = SourceValidator()

# Load sources
with open('sources_config.json') as f:
    config = json.load(f)

# Validate
sources = [
    SourceMetadata(
        url=s['url'],
        source_type=SourceType[s['type'].upper()],
        domain=s['domain'],
        author=s['author'],
        name=s['name'],
        subscribers_followers=s.get('subscribers', 0),
    )
    for s in config['sources']
]

results = validator.batch_validate_sources(sources)
print('✅ APPROVED:', len(results['approved']))
print('⏳ PENDING:', len(results['pending']))
print('❌ REJECTED:', len(results['rejected']))
"
```

---

## Phase 2: Content Extraction (Week 2)

### Step 2.1: Test Extractors

```bash
# Test YouTube extraction
python3 -c "
from content_extraction import YouTubeExtractor

extractor = YouTubeExtractor()
content = extractor.extract('https://www.youtube.com/watch?v=VIDEO_ID')
if content:
    print(f'✅ Extracted: {content.title}')
    print(f'Content length: {len(content.content)} chars')
"

# Test Blog extraction
python3 -c "
from content_extraction import BlogExtractor

extractor = BlogExtractor()
content = extractor.extract('https://example.com/article')
if content:
    print(f'✅ Extracted: {content.title}')
"

# Test RSS extraction
python3 -c "
from content_extraction import RSSFeedExtractor

extractor = RSSFeedExtractor()
contents = extractor.extract_feed('https://feeds.example.com/rss')
print(f'✅ Extracted {len(contents)} items from RSS feed')
"
```

### Step 2.2: Batch Extract from Sources

```python
from content_extraction import MultiSourceExtractor

extractor = MultiSourceExtractor()

sources = [
    "https://news.ycombinator.com/",
    "https://www.youtube.com/@ThePrimeagen/videos",
    "https://feeds.infoq.com/news",
]

for source in sources:
    content = extractor.extract(source)
    if content:
        print(f"✅ {content.title}")
```

---

## Phase 3: Vector Store Setup (Week 1)

### Step 3.1: Create Pinecone Index

```bash
# Install Pinecone CLI (optional)
pip install pinecone-client

# Create index via API (in Python)
python3 -c "
import pinecone

pinecone.init(
    api_key='YOUR_API_KEY',
    environment='us-east-1-aws'
)

# Create index
pinecone.create_index(
    name='tech-content-rag',
    dimension=1536,  # OpenAI ada-002
    metric='cosine',
    spec=pinecone.ServerlessSpec(
        cloud='aws',
        region='us-east-1'
    )
)

print('✅ Index created')
"
```

### Step 3.2: Initialize RAG System

```bash
python3 -c "
from rag_system import TechContentRAG
import os

rag = TechContentRAG(
    pinecone_api_key=os.getenv('PINECONE_API_KEY'),
    pinecone_env=os.getenv('PINECONE_ENV'),
    openai_api_key=os.getenv('OPENAI_API_KEY'),
)

rag.initialize_index()
print('✅ RAG system initialized')
"
```

---

## Phase 4: Ingestion Automation (Week 3-4)

### Step 4.1: Install Airflow

```bash
# Set Airflow home
export AIRFLOW_HOME=./airflow

# Initialize Airflow database
airflow db init

# Create admin user
airflow users create \
    --username admin \
    --password admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com

# Start Airflow webserver (in background)
airflow webserver -p 8080 &

# Start scheduler
airflow scheduler &
```

### Step 4.2: Configure and Deploy DAG

```bash
# Copy DAG to Airflow directory
cp airflow_rag_dag.py $AIRFLOW_HOME/dags/

# Reload DAGs
airflow dags list

# Enable DAG
airflow dags unpause tech_content_rag_daily

# Trigger manually to test
airflow dags test tech_content_rag_daily 2024-01-01
```

### Step 4.3: Configure Airflow Variables

```bash
# Set trusted sources config in Airflow
airflow variables set TRUSTED_SOURCES_CONFIG '{
  "sources": [
    {
      "url": "https://news.ycombinator.com/",
      "type": "news",
      "domain": "news.ycombinator.com",
      "author": "YCombinator",
      "name": "Hacker News",
      "subscribers": 500000,
      "credibility_score": 1.0
    }
  ]
}'
```

---

## Phase 5: RAG API (Week 5-6)

### Step 5.1: Start API Server

```bash
# Install API dependencies
pip install fastapi uvicorn pydantic

# Start server
python3 rag_api.py

# Or use uvicorn directly
uvicorn rag_api:app --host 0.0.0.0 --port 8000 --reload
```

### Step 5.2: Test Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Query example
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the latest Kubernetes improvements?",
    "num_sources": 5,
    "min_credibility": 0.7
  }'

# Generate content
curl -X POST http://localhost:8000/generate-content \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Best practices for microservices architecture",
    "content_type": "blog_post",
    "tone": "technical",
    "target_length": "long",
    "num_sources": 5
  }'
```

### Step 5.3: API Documentation

```bash
# Open Swagger UI
open http://localhost:8000/docs

# Open ReDoc
open http://localhost:8000/redoc
```

---

## Phase 6: Integration with Content Pipeline

### Example: Blog Generation Workflow

```python
import requests
import json

# Step 1: Generate content using RAG
response = requests.post('http://localhost:8000/generate-content', json={
    'query': 'How to optimize Kubernetes cluster costs in 2024',
    'content_type': 'blog_post',
    'tone': 'technical',
    'target_length': 'long',
    'num_sources': 5,
    'min_credibility': 0.75,
})

result = response.json()

# Step 2: Extract content and citations
blog_content = result['generated_content']
citations = result['citations']

# Step 3: Format with citations
formatted = f"""
{blog_content}

## Sources

"""

for i, citation in enumerate(citations, 1):
    formatted += f"""
{i}. **{citation['title']}** by {citation['author']}
   - URL: {citation['url']}
   - Credibility: {citation['credibility_score']:.2f}
   - Published: {citation['published_date']}
   - [Full excerpt](#)

"""

# Step 4: Publish to blog platform
# (integrate with your blogging system)
print(formatted)
```

---

## Monitoring & Operations

### Health Checks

```bash
# Check RAG system health
curl http://localhost:8000/health

# Check Airflow scheduler
airflow dags list

# Check Pinecone index stats
python3 -c "
import pinecone
pinecone.init(api_key='KEY', environment='ENV')
index = pinecone.Index('tech-content-rag')
print(index.describe_index_stats())
"
```

### Logging & Debugging

```bash
# View Airflow DAG logs
airflow logs tech_content_rag_daily validate_sources 2024-01-01

# View API logs
tail -f api_logs.log

# PostgreSQL query metrics
psql tech_content_rag -c "SELECT COUNT(*) FROM content_metadata;"
```

---

## Performance Tuning

### Embedding Optimization

```python
# Use smaller embedding model for faster ingestion
from llama_index.embeddings.openai import OpenAIEmbedding

embed_model = OpenAIEmbedding(
    model="text-embedding-3-small",  # 512 dims, faster
    # vs "text-embedding-3-large"   # 3072 dims, more accurate
)
```

### Query Optimization

```python
# Use hybrid search
results = rag_system.hybrid_search(
    query_text="kubernetes best practices",
    top_k=10,
)

# Apply metadata filtering
filtered = [
    r for r in results
    if r['credibility_score'] >= 0.75
    and r['source_type'] in ['blog', 'documentation']
]
```

---

## Scaling Considerations

### For Production:

1. **Pinecone Pod**: Upgrade from Serverless to Pod for higher throughput
   ```
   Serverless: ~100 QPS
   P1 Pod: ~1000 QPS
   ```

2. **PostgreSQL**: Use RDS or managed Postgres for metadata
   - Enable connection pooling (pgBouncer)
   - Set up read replicas for reporting

3. **Airflow**: Deploy on Kubernetes
   ```bash
   # Use Helm chart
   helm repo add apache-airflow https://airflow.apache.org
   helm install airflow apache-airflow/airflow
   ```

4. **API**: Deploy with multiple workers
   ```bash
   gunicorn rag_api:app -w 4 -b 0.0.0.0:8000
   ```

5. **Caching**: Add Redis for query caching
   ```python
   from redis import Redis
   cache = Redis(host='localhost', port=6379)
   ```

---

## Troubleshooting

### Issue: Pinecone Authentication Error
```bash
# Verify API key
echo $PINECONE_API_KEY

# Test connection
python3 -c "
import pinecone
pinecone.init(api_key='$PINECONE_API_KEY', environment='$PINECONE_ENV')
print(pinecone.list_indexes())
"
```

### Issue: Slow Embeddings
```bash
# Switch to smaller model
# text-embedding-3-small: 512 dims, faster
# text-embedding-3-large: 3072 dims, slower

# Consider batch processing
# Process 100 docs at a time instead of 1-by-1
```

### Issue: Low Query Results
```bash
# Check source credibility scores
# Verify min_credibility threshold
# Add more trusted sources
# Check vector store has data
```

---

## Success Metrics

Track these KPIs:

```python
{
    'ingestion': {
        'documents_per_day': 150,
        'deduplication_rate': 0.15,  # 15% duplicates removed
        'average_credibility': 0.82,
    },
    'retrieval': {
        'avg_relevance_score': 0.78,
        'sources_per_query': 4.5,
        'latency_p99': 1200,  # ms
    },
    'generation': {
        'citations_per_content': 4.2,
        'avg_generation_time': 3500,  # ms
        'user_satisfaction': 0.85,
    },
    'costs': {
        'monthly_embeddings': '$120',
        'monthly_llm': '$400',
        'monthly_storage': '$50',
    }
}
```

---

## Next Steps

1. **Week 1**: Set up environment, validate sources
2. **Week 2**: Implement extractors, test on 5-10 sources
3. **Week 3**: Set up vector store, batch ingest
4. **Week 4**: Deploy Airflow, automate ingestion
5. **Week 5**: Deploy API, integrate with blog pipeline
6. **Week 6**: Monitor, optimize, add more sources
7. **Week 7**: Scale up, prepare for production

---

## Resources

- **LlamaIndex Docs**: https://docs.llamaindex.ai/
- **Pinecone Docs**: https://docs.pinecone.io/
- **OpenAI API**: https://platform.openai.com/docs/
- **Airflow Docs**: https://airflow.apache.org/docs/
- **FastAPI Docs**: https://fastapi.tiangolo.com/

