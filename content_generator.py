"""
Jarvis RAG — Content Generator
Generates YouTube Shorts scripts, blog posts, Twitter threads from RAG context.
Optimized for RunPod RTX 4090 with Ollama.
"""
import json
import re
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_community.llms import Ollama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from config import CONFIG


@dataclass
class GeneratedContent:
    """Output from content generation."""
    content_type: str
    title: str
    body: str
    sources: List[Dict[str, Any]]
    credibility_avg: float
    word_count: int
    estimated_duration: str  # For video
    hashtags: List[str]
    generated_at: str

    def to_dict(self) -> Dict:
        return {
            "content_type": self.content_type,
            "title": self.title,
            "body": self.body,
            "sources": self.sources,
            "credibility_avg": self.credibility_avg,
            "word_count": self.word_count,
            "estimated_duration": self.estimated_duration,
            "hashtags": self.hashtags,
            "generated_at": self.generated_at,
        }


class ContentGenerator:
    """Generate monetizable content from RAG-retrieved context."""

    SYSTEM_PROMPT = """You are Jarvis, a tech content creator with 15+ years of experience.
Your content is known for being accurate, insightful, and viral.

CRITICAL RULES:
- Use ONLY the provided verified context. NEVER hallucinate facts.
- If context doesn't answer, say "I don't have verified info on this."
- Always cite sources with [Source: Name] inline.
- Be concise, punchy, and attention-grabbing.
- Include surprising or counter-intuitive insights.
"""

    def __init__(self):
        self.llm_config = CONFIG.get_llm_config()

        if self.llm_config["provider"] == "ollama":
            self.llm = Ollama(
                model=self.llm_config["model"],
                base_url=self.llm_config["base_url"],
                temperature=0.7,  # Higher for creative content
                num_ctx=4096,
                num_predict=1024,
            )
        else:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.llm_config["api_key"])
            self.model = self.llm_config["model"]

    def _build_context(self, docs: List[Document], max_chars: int = 4000) -> str:
        """Build context string from retrieved docs."""
        parts = []
        total = 0

        for doc in docs:
            source = doc.metadata.get("source_name", "Unknown")
            tier = doc.metadata.get("source_tier", "unknown")
            score = doc.metadata.get("credibility_score", 0)
            url = doc.metadata.get("url", "")

            entry = f"""[Source: {source} | Tier: {tier} | Credibility: {score}]
{doc.page_content}
URL: {url}
"""
            if total + len(entry) > max_chars:
                break
            parts.append(entry)
            total += len(entry)

        return "
---
".join(parts)

    def _extract_sources(self, docs: List[Document]) -> List[Dict]:
        """Extract source metadata for citations."""
        sources = []
        seen = set()
        for doc in docs:
            name = doc.metadata.get("source_name", "Unknown")
            if name in seen:
                continue
            seen.add(name)
            sources.append({
                "name": name,
                "tier": doc.metadata.get("source_tier", "unknown"),
                "credibility": doc.metadata.get("credibility_score", 0),
                "url": doc.metadata.get("url", ""),
                "published": doc.metadata.get("published", ""),
            })
        return sources

    def _avg_credibility(self, docs: List[Document]) -> float:
        """Average credibility of sources used."""
        if not docs:
            return 0
        scores = [d.metadata.get("credibility_score", 0) for d in docs]
        return round(sum(scores) / len(scores), 3)

    def _generate_hashtags(self, topic: str, categories: List[str]) -> List[str]:
        """Generate relevant hashtags."""
        base_tags = ["#tech", "#technology", "#ai", "#coding", "#developer"]
        topic_tags = [f"#{t.lower().replace(' ', '')}" for t in categories[:3]]
        return list(set(base_tags + topic_tags))[:5]

    # ── YouTube Shorts Script ────────────────────────────────────────────────

    def generate_youtube_shorts(self, topic: str, docs: List[Document]) -> GeneratedContent:
        """Generate a 60-second YouTube Shorts script."""
        context = self._build_context(docs)

        prompt = f"""Create a VIRAL YouTube Shorts script about: {topic}

VERIFIED CONTEXT:
{context}

FORMAT:
[HOOK] — First 3 seconds must GRAB attention
[MAIN] — 1 surprising insight + 1 counter-intuitive fact
[CTA] — Clear call-to-action (subscribe, comment, follow)

RULES:
- Under 150 words (60 seconds at normal speaking pace)
- Use short, punchy sentences
- Include ONE "wait, what?" moment
- End with a question to drive comments
- Cite sources with [Source: Name]

Script:"""

        if self.llm_config["provider"] == "ollama":
            response = self.llm.invoke(prompt)
        else:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=0.7,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            ).content[0].text

        sources = self._extract_sources(docs)

        return GeneratedContent(
            content_type="youtube_shorts",
            title=f"{topic} — Explained in 60 Seconds",
            body=response.strip(),
            sources=sources,
            credibility_avg=self._avg_credibility(docs),
            word_count=len(response.split()),
            estimated_duration="~60 seconds",
            hashtags=self._generate_hashtags(topic, [s["name"] for s in sources]),
            generated_at=datetime.now().isoformat(),
        )

    # ── Blog Post ────────────────────────────────────────────────────────────

    def generate_blog_post(self, topic: str, docs: List[Document], 
                          tone: str = "technical") -> GeneratedContent:
        """Generate an 800-1500 word blog post."""
        context = self._build_context(docs, max_chars=6000)

        prompt = f"""Write a {tone} blog post about: {topic}

VERIFIED CONTEXT:
{context}

FORMAT:
# Title (catchy, SEO-optimized)
## Introduction (hook the reader)
## Main Section 1 (key insight)
## Main Section 2 (counter-argument or deeper dive)
## Main Section 3 (practical application)
## Conclusion (summary + CTA)

RULES:
- 800-1500 words
- Use H2/H3 headers
- Include code blocks if relevant
- Cite sources with [Source: Name]
- Add a "Key Takeaways" bullet list
- End with a question for engagement

Blog Post:"""

        if self.llm_config["provider"] == "ollama":
            response = self.llm.invoke(prompt)
        else:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                temperature=0.5,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            ).content[0].text

        sources = self._extract_sources(docs)

        return GeneratedContent(
            content_type="blog_post",
            title=self._extract_title(response) or f"{topic}: A Deep Dive",
            body=response.strip(),
            sources=sources,
            credibility_avg=self._avg_credibility(docs),
            word_count=len(response.split()),
            estimated_duration="~5-8 min read",
            hashtags=self._generate_hashtags(topic, [s["name"] for s in sources]),
            generated_at=datetime.now().isoformat(),
        )

    # ── Twitter Thread ─────────────────────────────────────────────────────────

    def generate_twitter_thread(self, topic: str, docs: List[Document]) -> GeneratedContent:
        """Generate a 5-10 tweet thread."""
        context = self._build_context(docs, max_chars=3000)

        prompt = f"""Create a viral Twitter/X thread about: {topic}

VERIFIED CONTEXT:
{context}

FORMAT:
Tweet 1/🧵: Hook (must stop the scroll)
Tweet 2: Context/background
Tweet 3: The surprising insight
Tweet 4: Counter-intuitive fact
Tweet 5: Practical takeaway
Tweet 6: CTA (follow, RT, comment)

RULES:
- Each tweet under 280 characters
- Use line breaks for readability
- Include 1-2 relevant hashtags per tweet
- Make Tweet 1 impossible to ignore
- Cite sources with [Source: Name]

Thread:"""

        if self.llm_config["provider"] == "ollama":
            response = self.llm.invoke(prompt)
        else:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                temperature=0.8,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            ).content[0].text

        sources = self._extract_sources(docs)

        return GeneratedContent(
            content_type="twitter_thread",
            title=f"🧵 {topic}",
            body=response.strip(),
            sources=sources,
            credibility_avg=self._avg_credibility(docs),
            word_count=len(response.split()),
            estimated_duration="~2 min read",
            hashtags=self._generate_hashtags(topic, [s["name"] for s in sources]),
            generated_at=datetime.now().isoformat(),
        )

    # ── Newsletter Summary ──────────────────────────────────────────────────

    def generate_newsletter(self, topics: List[str], docs: List[Document]) -> GeneratedContent:
        """Generate a weekly newsletter covering multiple topics."""
        context = self._build_context(docs, max_chars=8000)

        prompt = f"""Write a weekly tech newsletter covering: {', '.join(topics)}

VERIFIED CONTEXT:
{context}

FORMAT:
# This Week in Tech
## 🚀 Top Story (biggest news)
## 📊 Trend Analysis (what's moving)
## 💡 Deep Dive (one topic explained)
## 🛠️ Tool of the Week
## 📚 Resources (links from context)

RULES:
- Conversational, insider tone
- 1000-1500 words
- Include source URLs
- Add "Forward to a friend" CTA
- Credibility scores for each source

Newsletter:"""

        if self.llm_config["provider"] == "ollama":
            response = self.llm.invoke(prompt)
        else:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                temperature=0.6,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            ).content[0].text

        sources = self._extract_sources(docs)

        return GeneratedContent(
            content_type="newsletter",
            title=f"This Week in Tech — {datetime.now().strftime('%b %d, %Y')}",
            body=response.strip(),
            sources=sources,
            credibility_avg=self._avg_credibility(docs),
            word_count=len(response.split()),
            estimated_duration="~5 min read",
            hashtags=["#newsletter", "#technews", "#weeklydigest"],
            generated_at=datetime.now().isoformat(),
        )

    def _extract_title(self, text: str) -> Optional[str]:
        """Extract title from markdown heading."""
        match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
        return match.group(1) if match else None

    def save_content(self, content: GeneratedContent, 
                    output_dir: str = "/workspace/output"):
        """Save generated content to file."""
        from pathlib import Path
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        filename = f"{content.content_type}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        path = Path(output_dir) / filename

        with open(path, "w") as f:
            json.dump(content.to_dict(), f, indent=2)

        print(f"💾 Saved to {path}")
        return path


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from rag_engine import RAGEngine

    # Setup
    engine = RAGEngine()
    generator = ContentGenerator()

    # Test data
    test_docs = [
        Document(
            page_content="Kubernetes is the industry standard for container orchestration. It was originally designed by Google engineers in 2014 and is now maintained by the Cloud Native Computing Foundation. Over 96% of organizations use Kubernetes in production.",
            metadata={
                "source_name": "AWS News Blog",
                "source_tier": "tier_1",
                "credibility_score": 0.95,
                "url": "https://aws.amazon.com/blogs/aws/",
                "published": "2026-04-15",
            }
        ),
        Document(
            page_content="Despite its popularity, Kubernetes has a steep learning curve. A 2025 survey found that 67% of developers struggle with Kubernetes networking and service mesh configuration.",
            metadata={
                "source_name": "The Verge",
                "source_tier": "tier_2",
                "credibility_score": 0.80,
                "url": "https://www.theverge.com",
                "published": "2026-03-20",
            }
        ),
    ]

    # Generate content
    print("🎬 Generating YouTube Shorts...")
    shorts = generator.generate_youtube_shorts("Kubernetes in 2026", test_docs)
    print(f"   ✅ {shorts.word_count} words, avg credibility: {shorts.credibility_avg}")

    print("
📝 Generating Blog Post...")
    blog = generator.generate_blog_post("Why Kubernetes Still Dominates", test_docs)
    print(f"   ✅ {blog.word_count} words, avg credibility: {blog.credibility_avg}")

    print("
🐦 Generating Twitter Thread...")
    thread = generator.generate_twitter_thread("Kubernetes myths", test_docs)
    print(f"   ✅ {thread.word_count} words, avg credibility: {thread.credibility_avg}")

    # Save
    generator.save_content(shorts)
    generator.save_content(blog)
