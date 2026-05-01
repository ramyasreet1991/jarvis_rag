# Technology Content RAG System - Quick Reference

## 📁 Project Structure

```
tech-content-rag/
├── source_validation.py          # Source credibility scoring
├── content_extraction.py         # Extract from YouTube, blogs, RSS, podcasts
├── rag_system.py                 # LlamaIndex + Pinecone integration
├── rag_api.py                    # FastAPI endpoints for generation
├── airflow_rag_dag.py            # Airflow orchestration
│
├── config.json                   # Trusted sources & settings
├── requirements.txt              # Python dependencies
├── .env                          # Environment variables
│
├── IMPLEMENTATION_GUIDE.md       # Step-by-step setup
├── rag_system_architecture.md    # System design & flow
└── README.md                     # This file
```

---

## 🚀 30-Minute Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
export $(cat .env | xargs)
```

### 2. Initialize RAG System
```bash
python3 -c "
from rag_system import TechContentRAG
rag = TechContentRAG(
    pinecone_api_key='$PINECONE_API_KEY',
    pinecone_env='$PINECONE_ENV',
    openai_api_key='$OPENAI_API_KEY'
)
rag.initialize_index()
print('✅ RAG initialized')
"
```

### 3. Test Content Extraction
```bash
python3 -c "
from content_extraction import YouTubeExtractor
extractor = YouTubeExtractor()
content = extractor.extract('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
print(f'✅ Extracted: {content.title if content else \"Failed\"}')
"
```

### 4. Start API Server
```bash
python3 rag_api.py
# Visit http://localhost:8000/docs
```

---

## 🔑 Core Concepts

### Source Validation (0-1 Scale)
- **Domain Authority** (0.25): Tier ranking, trust history
- **Author Reputation** (0.25): Verification status, followers
- **Content Quality** (0.20): Length, structure, citations
- **Citation Density** (0.15): External references per paragraph
- **Update Freshness** (0.10): Time since last update
- **Community** (0.05): Followers, subscribers, engagement

**Minimum to Ingest: 0.65**

### Content Chunking Strategy
- **Size**: 500 tokens, 100-token overlap
- **Method**: Semantic chunks where possible
- **Metadata**: Title, author, URL, date, credibility score

### Retrieval Pipeline
```
User Query
    ↓
[Semantic Search] → Top 10 similar chunks
    ↓
[Filter] → Only credibility ≥ 0.65
    ↓
[Re-rank] → Re-order by relevance
    ↓
[Extract] → Return top 5 with citations
```

---

## 📊 API Endpoints

### Query (Search)
```bash
POST /query
{
  "query": "Kubernetes networking best practices",
  "num_sources": 5,
  "min_credibility": 0.7
}
```
Returns: Response + Citations with metadata

### Generate Content
```bash
POST /generate-content
{
  "query": "Latest in AI safety research",
  "content_type": "blog_post|twitter_thread|youtube_script|newsletter",
  "tone": "informative|casual|technical|executive",
  "target_length": "short|medium|long",
  "num_sources": 5
}
```
Returns: Generated content + Citations

### Ingest Content
```bash
POST /ingest
{
  "content_list": [
    {
      "title": "...",
      "content": "...",
      "author": "...",
      "url": "...",
      "source_type": "youtube|podcast|blog|news",
      "credibility_score": 0.85
    }
  ]
}
```

### Health Check
```bash
GET /health
```

---

## 🔄 Daily Ingestion Workflow (via Airflow)

```
2:00 AM UTC
    ↓
[Validate] Sources (credibility scoring)
    ↓
[Extract] Content from approved sources
    ↓
[Deduplicate] Remove hash-based duplicates
    ↓
[Ingest] Into Pinecone + metadata DB
    ↓
[Report] Summary of run
    ↓
Complete
```

---

## 📈 Metrics to Track

| Metric | Target | Frequency |
|--------|--------|-----------|
| Documents ingested/day | 100+ | Daily |
| Avg credibility score | 0.78+ | Daily |
| Query latency (P99) | <1.5s | Real-time |
| Retrieval precision@5 | 0.80+ | Weekly |
| Citations per content | 3-5 | Per generation |
| Monthly ingestion cost | <$200 | Monthly |

---

## 🔌 Integration Points

### With Your Blog Pipeline
```python
# In your blog generation script
from rag_api_client import generate_content

result = generate_content(
    query="Your blog topic",
    content_type="blog_post",
    tone="technical"
)

# Use result['generated_content'] + result['citations']
publish_blog(result)
```

### With Your YouTube Pipeline
```python
# Generate video scripts with citations
script = generate_content(
    query="Video topic",
    content_type="youtube_script",
    tone="casual"
)

# Script has [INTRO], [MAIN], [OUTRO] sections
create_video(script)
```

### With Hashnode Publishing
```python
# Auto-publish to Hashnode with citations
import hashnode_client

blog = generate_content(
    query="Topic",
    content_type="blog_post"
)

hashnode_client.publish(
    title=blog['title'],
    content=blog['generated_content'],
    tags=['kubernetes', 'devops']
)
```

---

## 🛠️ Configuration

### Add New Source
Edit `config.json`:
```json
{
  "sources": {
    "tier_2_blogs": [
      {
        "url": "https://your-blog.com/feed",
        "type": "rss",
        "name": "Your Blog",
        "credibility_score": 0.75
      }
    ]
  }
}
```

### Adjust Retrieval Settings
In `rag_system.py`:
```python
RETRIEVAL_CONFIG = {
    'top_k': 10,                    # Number of results
    'min_credibility': 0.65,        # Threshold
    'semantic_weight': 0.7,         # vs BM25
    'date_range': 'last_90_days',   # Recency
}
```

### Change Ingestion Schedule
In `airflow_rag_dag.py`:
```python
SCHEDULE_INTERVAL = '0 2 * * *'  # Daily at 2 AM UTC
# Cron: minute hour day month weekday
```

---

## 🚨 Troubleshooting

| Issue | Solution |
|-------|----------|
| **Low retrieval results** | ✓ Add more trusted sources ✓ Lower min_credibility ✓ Check vector DB has data |
| **Slow API responses** | ✓ Use smaller embedding model ✓ Add Redis caching ✓ Batch requests |
| **High costs** | ✓ Switch to text-embedding-3-small ✓ Reduce query frequency ✓ Use hybrid search |
| **Duplicate content** | ✓ Increase dedup threshold ✓ Add source to blacklist ✓ Manual review |
| **Pinecone auth fails** | ✓ Verify API key ✓ Check environment ✓ Test connection |

---

## 📚 Example: Blog Post Generation Workflow

```python
import requests
import os

# Step 1: Generate content
response = requests.post(f'http://localhost:8000/generate-content', json={
    'query': 'Kubernetes cluster optimization strategies',
    'content_type': 'blog_post',
    'tone': 'technical',
    'target_length': 'long',
    'num_sources': 5,
    'min_credibility': 0.75
})

result = response.json()

# Step 2: Extract content and citations
blog_content = result['generated_content']
citations = result['citations']

# Step 3: Format with markdown
markdown = f"""# {result['query']}

{blog_content}

## References

"""

for i, cite in enumerate(citations, 1):
    markdown += f"""
{i}. **{cite['title']}** by {cite['author']}
   - Published: {cite['published_date']}
   - Credibility: {cite['credibility_score']:.1%}
   - Source: {cite['url']}

"""

# Step 4: Publish to blog platform
# (Integrate with your Hashnode/Dev.to/Medium API)
publish_to_blog(markdown)

print("✅ Blog post published with citations!")
```

---

## 💡 Pro Tips

### Tip 1: Start Small
- Begin with 5-10 trusted sources
- Test extraction on each
- Gradually add more sources after validation

### Tip 2: Monitor Quality
- Track citation accuracy weekly
- Spot check generated content
- Adjust source credibility scores

### Tip 3: Optimize Costs
- Use text-embedding-3-small (not large)
- Batch API calls (100 at a time)
- Cache frequently asked questions
- Implement query deduplication

### Tip 4: Integrate Gradually
- Start with query API (just retrieving content)
- Then add generation (blog posts)
- Finally full automation (daily scheduling)

### Tip 5: Version Control Sources
- Keep config.json in git
- Tag source updates
- Track credibility score changes
- Document why sources added/removed

---

## 🎯 Success Checklist

- [ ] Environment variables configured (.env)
- [ ] Pinecone index created
- [ ] Content extractors tested on 5 sources
- [ ] RAG system initialized
- [ ] API server running & docs accessible
- [ ] Airflow DAG deployed & tested
- [ ] Ingestion pipeline run successfully once
- [ ] Query API returning results
- [ ] Content generation producing citations
- [ ] Integration with blog pipeline working

---

## 📞 Support & Resources

- **LlamaIndex Docs**: https://docs.llamaindex.ai/
- **Pinecone Docs**: https://docs.pinecone.io/
- **FastAPI Tutorial**: https://fastapi.tiangolo.com/
- **Airflow Guide**: https://airflow.apache.org/docs/

---

## 🔐 Security Notes

1. **Never commit `.env`** - Use environment variables
2. **Rotate API keys regularly** - Monthly minimum
3. **Use HTTPS in production** - FastAPI + reverse proxy
4. **Validate sources carefully** - Credibility is foundation
5. **Monitor for hallucinations** - Review AI-generated content

---

## 📝 Citation Format

Generated content includes:
```markdown
According to [Source 1], <claim>.

[Source 1]: Title - Author (Credibility: 0.85)
URL: https://...
Published: 2024-01-15
```

---

**Last Updated**: January 2024
**Version**: 1.0.0
**Status**: Production Ready

