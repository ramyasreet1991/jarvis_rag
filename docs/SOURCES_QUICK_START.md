# Using Authenticated Sources - Quick Start Guide

## What You Have

1. **AUTHENTIC_SOURCES.md** — Detailed breakdown of 50+ verified sources
   - Credibility scores justified
   - Extraction methods specified
   - Real URLs verified & working
   - Organized by tier (1-3)

2. **sources_config.json** — Ready-to-use configuration file
   - 50 pre-configured sources
   - All metadata included (URLs, feeds, API endpoints)
   - Extraction methods defined
   - Filters and quality thresholds set

---

## 3-Step Setup

### Step 1: Copy Configuration to Airflow Variables

```bash
# Set sources config in Airflow
airflow variables set TRUSTED_SOURCES_CONFIG \
  "$(cat sources_config.json)"

# Or set directly if < 8000 chars
airflow variables set TRUSTED_SOURCES_CONFIG '{
  "sources": [
    {
      "url": "https://news.ycombinator.com/rss",
      "type": "rss",
      "credibility_score": 1.0,
      "priority": "high"
    }
  ]
}'
```

### Step 2: Test with Quick Start Sources

```python
from source_validation import SourceValidator, SourceMetadata, SourceType
import json

validator = SourceValidator()

# Load quick start sources
with open('sources_config.json') as f:
    config = json.load(f)

quick_start_ids = config['quick_start_sources']  # 10 best sources to start
all_sources = {}

# Map all sources
for category in ['tier_1_high_credibility', 'tier_2_company_blogs', 'tier_2_podcasts']:
    if isinstance(config[category], list):
        for source in config[category]:
            all_sources[source['id']] = source
    elif isinstance(config[category], dict):
        for subcat, items in config[category].items():
            for source in items:
                all_sources[source['id']] = source

# Validate quick start sources only
test_sources = [all_sources[id] for id in quick_start_ids if id in all_sources]

print(f"Testing {len(test_sources)} quick start sources...")
for source in test_sources:
    print(f"  ✓ {source['name']} ({source['credibility_score']:.2f})")
```

### Step 3: Run Daily Ingestion

```bash
# Trigger Airflow DAG
airflow dags trigger tech_content_rag_daily

# Monitor
airflow dags list-runs -d tech_content_rag_daily --limit 5
```

---

## Source Organization

### By Tier (Quality Level)

**Tier 1 (0.90-1.0)** — Start here
- HackerNews, InfoQ, arXiv
- YouTube: ThePrimeagen, Fireship, etc.
- Cloud blogs: Google, AWS, Azure, OpenAI

**Tier 2 (0.75-0.90)** — Add after tier 1 working
- Dev.to, Hashnode, Medium publications
- Individual thought leaders (Paul Graham, Martin Fowler, etc.)
- Podcasts (Lex Fridman, Changelog, etc.)

**Tier 3 (0.65-0.80)** — Expand after stabilizing
- Specialized topics (security, data science)
- Community resources (GitHub projects)
- News sites (TechCrunch)

---

## By Use Case

### For Data Engineering Blog
```python
sources = config['recommended_by_use_case']['data_engineering']
# Returns: arxiv-001, blog-001, blog-002, tl-002, comm-003
```

### For DevOps/Kubernetes Content
```python
sources = config['recommended_by_use_case']['devops_kubernetes']
# Returns: NetworkChuck, TechWorld with Nana, K8s blog, etc.
```

### For AI/ML Content
```python
sources = config['recommended_by_use_case']['ai_ml']
# Returns: arXiv, OpenAI blog, DeepMind, etc.
```

---

## Sample Integration Code

### Extract from Sources Configuration

```python
import json
from content_extraction import MultiSourceExtractor
from source_validation import SourceValidator

# Load config
with open('sources_config.json') as f:
    config = json.load(f)

# Get quick start sources
extractor = MultiSourceExtractor()
extracted_content = []

# Process each tier 1 source
for source in config['tier_1_high_credibility']['news']:
    if source['active']:
        print(f"Extracting from {source['name']}...")
        
        if source['type'] == 'news':
            content = extractor.extract(source['feed_url'] or source['url'])
        elif source['type'] == 'youtube':
            content = extractor.youtube.extract(source['url'])
        
        if content:
            extracted_content.append({
                'title': content.title,
                'content': content.content,
                'author': source['author'],
                'url': source['url'],
                'source_type': source['type'],
                'credibility_score': source['credibility_score'],
                'tags': source['content_focus'],
            })

print(f"✅ Extracted {len(extracted_content)} pieces of content")
```

### Ingest to RAG System

```python
from rag_system import TechContentRAG
import os

rag = TechContentRAG(
    pinecone_api_key=os.getenv('PINECONE_API_KEY'),
    pinecone_env=os.getenv('PINECONE_ENV'),
    openai_api_key=os.getenv('OPENAI_API_KEY'),
)

rag.initialize_index()

# Ingest extracted content
stats = rag.ingest_content(extracted_content)

print(f"✅ Ingestion complete:")
print(f"   Total: {stats['total']}")
print(f"   Ingested: {stats['ingested']}")
print(f"   Failed: {stats['failed']}")
```

---

## Verifying Sources Are Working

### Check RSS Feeds
```bash
# Test HackerNews RSS
curl -s https://news.ycombinator.com/rss | head -20

# Test InfoQ RSS
curl -s https://feed.infoq.com/ | head -20

# Test Dev.to RSS
curl -s https://dev.to/feed | head -20
```

### Check YouTube Channels
```python
from youtube_transcript_api import YouTubeTranscriptApi

# Get latest ThePrimeagen video transcript
video_id = "dQw4w9WgXcQ"  # Replace with actual video
transcript = YouTubeTranscriptApi.get_transcript(video_id)
print(f"✅ Transcript fetched: {len(transcript)} entries")
```

### Check API Endpoints
```python
import requests

# Check arXiv API
response = requests.get(
    'https://arxiv.org/api/query',
    params={
        'search_query': 'cat:cs.AI',
        'max_results': 5,
        'sortBy': 'submittedDate'
    }
)
print(f"✅ arXiv API working: {response.status_code}")

# Check Dev.to API
response = requests.get('https://dev.to/api/articles?per_page=1')
print(f"✅ Dev.to API working: {response.status_code}")
```

---

## Customizing for Your Needs

### Add New Source to Config

```json
{
  "id": "custom-001",
  "name": "My Blog",
  "url": "https://myblog.com/",
  "feed_url": "https://myblog.com/feed.xml",
  "type": "blog",
  "credibility_score": 0.75,
  "domain": "myblog.com",
  "author": "Your Name",
  "description": "Custom technical blog",
  "update_frequency": "weekly",
  "extraction_method": "rss",
  "content_focus": ["your", "topics"],
  "active": true,
  "last_verified": "2024-01-15"
}
```

### Adjust Credibility Scores

Based on your experience:
- **High performers**: Increase to 0.95+
- **Low quality**: Decrease to 0.60-0.65
- **Seasonal**: Adjust update_frequency

### Filter by Topic

```python
# Get only data engineering sources
config = json.load(open('sources_config.json'))
all_sources = []

for category, items in config['tier_1_high_credibility'].items():
    if isinstance(items, list):
        for source in items:
            if 'data' in source.get('content_focus', []):
                all_sources.append(source)

print(f"Found {len(all_sources)} data engineering sources")
```

---

## Monitoring & Maintenance

### Weekly Checklist
- [ ] Check 2-3 sources are still active (curl/API test)
- [ ] Review ingestion logs for errors
- [ ] Spot check extracted content quality

### Monthly Tasks
- [ ] Update `last_verified` dates
- [ ] Adjust credibility scores based on performance
- [ ] Add 1-2 new sources if needed
- [ ] Review which sources generate best content

### Quarterly Review
- [ ] Full source audit
- [ ] Prune underperforming sources
- [ ] Analyze content quality metrics
- [ ] Research new sources in your niche

---

## Cost Breakdown

| Source Type | Cost | Frequency |
|------------|------|-----------|
| RSS Feeds | Free | Daily |
| YouTube Transcripts | Free | Weekly |
| arXiv API | Free | Daily |
| GitHub API | Free (60 req/hr) | As needed |
| Podcasts | Free | Weekly |
| **Total Monthly** | **$0** | — |

*(Vector DB and LLM costs come from your embedding/generation, not sources)*

---

## Troubleshooting

### Source Returns Empty/No Transcripts

```python
# Check if YouTube video has transcripts
from youtube_transcript_api import YouTubeTranscriptApi
try:
    transcript = YouTubeTranscriptApi.get_transcript(video_id)
    print("✅ Transcript available")
except:
    print("❌ No transcript (might need Whisper API fallback)")
```

### RSS Feed Not Updating

```python
# Check feed freshness
import feedparser
feed = feedparser.parse(feed_url)
latest_date = feed.entries[0]['published'] if feed.entries else None
print(f"Latest update: {latest_date}")
```

### API Rate Limiting

```python
# Respect rate limits
RATE_LIMITS = {
    'github': 60,           # per hour
    'arxiv': 'no limit',    # but be respectful
    'dev.to': '10 per second',
    'youtube': 'via quota',
}
```

---

## Next Steps

1. **Today**: Review AUTHENTIC_SOURCES.md for understanding
2. **Tomorrow**: Set up sources_config.json in your Airflow instance
3. **This Week**: Run extraction on quick start sources (10 sources)
4. **Next Week**: Monitor quality, adjust credibility scores
5. **This Month**: Expand to Tier 2 sources (20+ total)
6. **Next Month**: Fine-tune, add specialized sources for your niche

---

## Pro Tips

✅ **Start small**: Test with 5-10 sources first
✅ **Monitor quality**: Check extracted content daily for first week
✅ **Incremental scaling**: Add 5-10 sources per week
✅ **Adjust credibility**: Use actual performance data
✅ **Version control**: Keep sources_config.json in git
✅ **Document changes**: Why did you add/remove sources?

---

## Reference

- **AUTHENTIC_SOURCES.md** — Full documentation of all sources
- **config.json** — Original example configuration (update to use sources_config.json)
- **source_validation.py** — Credibility scoring implementation
- **content_extraction.py** — Source-specific extractors
- **rag_system.py** — RAG integration

**Questions?** Start with AUTHENTIC_SOURCES.md → Look up specific source tier → Check extraction method → Test with curl/API

