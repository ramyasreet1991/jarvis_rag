"""
Jarvis RAG — Source Vetting Engine
Validates authenticity before ANY content enters the knowledge base.
Runs on CPU (lightweight), blocks bad sources at the gate.
"""
import json
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
from datetime import datetime
import re
import requests
from bs4 import BeautifulSoup
import feedparser


class TrustTier(Enum):
    TIER_1 = "tier_1"      # 0.90-1.0 — Primary trusted
    TIER_2 = "tier_2"      # 0.75-0.90 — Quality community
    TIER_3 = "tier_3"      # 0.65-0.75 — Specialized/curated
    BLOCKED = "blocked"    # <0.65 — Rejected


@dataclass
class Source:
    name: str
    url: str
    feed_url: Optional[str] = None
    source_type: str = "blog"  # blog | youtube | podcast | news | research
    trust_tier: TrustTier = TrustTier.TIER_2
    credibility_score: float = 0.75
    categories: List[str] = field(default_factory=list)
    last_verified: str = ""
    author_verified: bool = False
    editorial_process: bool = False
    citation_density: float = 0.0
    subscriber_count: int = 0
    update_frequency: str = "weekly"  # hourly | daily | weekly | monthly
    extraction_method: str = "rss"    # rss | api | scrape | transcript

    def is_eligible(self, threshold: float = 0.65) -> bool:
        return self.credibility_score >= threshold

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "url": self.url,
            "feed_url": self.feed_url,
            "source_type": self.source_type,
            "trust_tier": self.trust_tier.value,
            "credibility_score": self.credibility_score,
            "categories": self.categories,
            "last_verified": self.last_verified,
            "author_verified": self.author_verified,
            "editorial_process": self.editorial_process,
            "citation_density": self.citation_density,
            "subscriber_count": self.subscriber_count,
            "update_frequency": self.update_frequency,
            "extraction_method": self.extraction_method,
        }


class SourceVetter:
    """6-factor credibility scoring engine."""

    WEIGHTS = {
        "domain_authority": 0.25,
        "author_reputation": 0.25,
        "content_quality": 0.20,
        "citation_density": 0.15,
        "update_freshness": 0.10,
        "community_validation": 0.05,
    }

    def __init__(self, threshold: float = 0.65):
        self.threshold = threshold
        self.verified_sources: Dict[str, Source] = {}
        self.blocked_domains: set = field(default_factory=set)

    def score_source(self, source: Source) -> Tuple[float, Dict]:
        """Score a source using 6 weighted factors."""
        scores = {}

        # 1. Domain Authority (0-1)
        scores["domain_authority"] = self._score_domain_authority(source)

        # 2. Author Reputation (0-1)
        scores["author_reputation"] = self._score_author_reputation(source)

        # 3. Content Quality (0-1)
        scores["content_quality"] = self._score_content_quality(source)

        # 4. Citation Density (0-1)
        scores["citation_density"] = min(source.citation_density / 3.0, 1.0)

        # 5. Update Freshness (0-1)
        scores["update_freshness"] = self._score_freshness(source)

        # 6. Community Validation (0-1)
        scores["community_validation"] = self._score_community(source)

        # Weighted total
        total = sum(scores[k] * self.WEIGHTS[k] for k in scores)

        # Assign tier
        if total >= 0.90:
            source.trust_tier = TrustTier.TIER_1
        elif total >= 0.75:
            source.trust_tier = TrustTier.TIER_2
        elif total >= self.threshold:
            source.trust_tier = TrustTier.TIER_3
        else:
            source.trust_tier = TrustTier.BLOCKED

        source.credibility_score = round(total, 3)
        return total, scores

    def _score_domain_authority(self, source: Source) -> float:
        """Score based on domain characteristics."""
        domain = source.url.split("/")[2] if "/" in source.url else source.url

        # Known high-authority domains
        tier_1_domains = [
            "arxiv.org", "news.ycombinator.com", "aws.amazon.com",
            "cloud.google.com", "openai.com", "deepmind.google",
            "research.google", "microsoft.com", "ieee.org", "acm.org",
        ]
        tier_2_domains = [
            "techcrunch.com", "theverge.com", "wired.com", "ars technica.com",
            "dev.to", "hashnode.dev", "medium.com", "substack.com",
        ]

        if any(d in domain for d in tier_1_domains):
            return 1.0
        if any(d in domain for d in tier_2_domains):
            return 0.85
        if ".edu" in domain or ".gov" in domain:
            return 0.95
        if source.editorial_process:
            return 0.75
        return 0.60

    def _score_author_reputation(self, source: Source) -> float:
        """Score based on author credentials."""
        if source.author_verified:
            return 1.0
        if source.source_type == "youtube" and source.subscriber_count > 500000:
            return 0.95
        if source.source_type == "youtube" and source.subscriber_count > 100000:
            return 0.85
        if source.source_type == "podcast" and source.subscriber_count > 50000:
            return 0.85
        if source.source_type in ["blog", "news"] and source.subscriber_count > 100000:
            return 0.80
        return 0.65

    def _score_content_quality(self, source: Source) -> float:
        """Score based on content depth indicators."""
        score = 0.70
        if source.editorial_process:
            score += 0.15
        if source.citation_density > 1.0:
            score += 0.10
        if source.source_type == "research":
            score += 0.15
        return min(score, 1.0)

    def _score_freshness(self, source: Source) -> float:
        """Score based on update frequency."""
        freq_map = {
            "hourly": 1.0, "daily": 0.95, "weekly": 0.85,
            "biweekly": 0.75, "monthly": 0.65,
        }
        return freq_map.get(source.update_frequency, 0.60)

    def _score_community(self, source: Source) -> float:
        """Score based on community metrics."""
        if source.subscriber_count > 1000000:
            return 1.0
        if source.subscriber_count > 500000:
            return 0.90
        if source.subscriber_count > 100000:
            return 0.75
        if source.subscriber_count > 10000:
            return 0.60
        return 0.40

    def verify_feed(self, source: Source) -> bool:
        """Verify RSS/feed URL is accessible and returns valid content."""
        if not source.feed_url:
            return True  # Skip if no feed
        try:
            feed = feedparser.parse(source.feed_url)
            return len(feed.entries) > 0
        except Exception:
            return False

    def vet_source(self, source: Source) -> Tuple[bool, str]:
        """Full vetting pipeline. Returns (passed, reason)."""
        # Check feed accessibility
        if source.feed_url and not self.verify_feed(source):
            return False, "Feed inaccessible or empty"

        # Score
        score, breakdown = self.score_source(source)

        # Check threshold
        if score < self.threshold:
            return False, f"Credibility score {score:.2f} below threshold {self.threshold}"

        # Store
        self.verified_sources[source.name] = source
        return True, f"Approved: {source.trust_tier.value} (score: {score:.2f})"

    def load_default_sources(self) -> List[Source]:
        """Load the pre-vetted 50+ tech sources."""
        return [
            # TIER 1 — Enterprise & Research
            Source("HackerNews", "https://news.ycombinator.com",
                   "https://news.ycombinator.com/rss", "news",
                   TrustTier.TIER_1, 1.0,
                   ["startups", "tech", "funding"], "2026-05-01",
                   True, True, 2.5, 500000, "hourly", "rss"),
            Source("arXiv CS", "https://arxiv.org",
                   "http://export.arxiv.org/rss/cs", "research",
                   TrustTier.TIER_1, 0.95,
                   ["ai", "ml", "systems"], "2026-05-01",
                   True, True, 5.0, 1000000, "daily", "rss"),
            Source("AWS News Blog", "https://aws.amazon.com/blogs/aws/",
                   "https://aws.amazon.com/blogs/aws/feed/", "blog",
                   TrustTier.TIER_1, 0.95,
                   ["cloud", "aws", "devops"], "2026-05-01",
                   True, True, 3.0, 200000, "daily", "rss"),
            Source("Google Cloud Blog", "https://cloud.google.com/blog",
                   "https://cloud.google.com/blog/rss", "blog",
                   TrustTier.TIER_1, 0.95,
                   ["cloud", "gcp", "data"], "2026-05-01",
                   True, True, 3.0, 150000, "daily", "rss"),
            Source("OpenAI Blog", "https://openai.com/blog",
                   "https://openai.com/blog/rss.xml", "blog",
                   TrustTier.TIER_1, 0.98,
                   ["ai", "llm", "research"], "2026-05-01",
                   True, True, 4.0, 500000, "weekly", "rss"),

            # TIER 1 — YouTube
            Source("Fireship", "https://www.youtube.com/@Fireship",
                   "https://www.youtube.com/feeds/videos.xml?channel_id=UCsBjURrPoezykLs9EqgamOA",
                   "youtube", TrustTier.TIER_1, 0.95,
                   ["web-dev", "tutorials", "quick-learn"], "2026-05-01",
                   True, False, 1.5, 3200000, "weekly", "transcript"),
            Source("ThePrimeagen", "https://www.youtube.com/@ThePrimeagen",
                   "https://www.youtube.com/feeds/videos.xml?channel_id=UC8ENHE5xdFSwx71u3fDH5Xw",
                   "youtube", TrustTier.TIER_1, 0.92,
                   ["backend", "rust", "systems"], "2026-05-01",
                   True, False, 1.0, 750000, "weekly", "transcript"),
            Source("NetworkChuck", "https://www.youtube.com/@NetworkChuck",
                   "https://www.youtube.com/feeds/videos.xml?channel_id=UC9x0AN7BWHpCDHSm9NiJFJQ",
                   "youtube", TrustTier.TIER_1, 0.90,
                   ["networking", "security", "devops"], "2026-05-01",
                   True, False, 1.0, 4500000, "weekly", "transcript"),

            # TIER 2 — Quality Community
            Source("TechCrunch", "https://techcrunch.com",
                   "https://techcrunch.com/feed/", "news",
                   TrustTier.TIER_2, 0.78,
                   ["startups", "funding", "tech"], "2026-05-01",
                   True, True, 2.0, 2000000, "daily", "rss"),
            Source("The Verge", "https://www.theverge.com",
                   "https://www.theverge.com/rss/index.xml", "news",
                   TrustTier.TIER_2, 0.80,
                   ["consumer-tech", "policy", "reviews"], "2026-05-01",
                   True, True, 2.0, 1500000, "daily", "rss"),
            Source("Dev.to", "https://dev.to",
                   "https://dev.to/feed", "blog",
                   TrustTier.TIER_2, 0.80,
                   ["tutorials", "community", "career"], "2026-05-01",
                   False, False, 1.0, 800000, "hourly", "rss"),
            Source("Hashnode", "https://hashnode.com",
                   "https://hashnode.com/rss", "blog",
                   TrustTier.TIER_2, 0.78,
                   ["tutorials", "community", "web"], "2026-05-01",
                   False, False, 1.0, 500000, "daily", "rss"),

            # TIER 2 — Podcasts
            Source("Lex Fridman Podcast", "https://lexfridman.com/podcast",
                   "https://lexfridman.com/feed/podcast/", "podcast",
                   TrustTier.TIER_2, 0.85,
                   ["ai", "science", "philosophy"], "2026-05-01",
                   True, True, 2.0, 5000000, "weekly", "transcript"),
            Source("Changelog", "https://changelog.com",
                   "https://changelog.com/podcast/feed", "podcast",
                   TrustTier.TIER_2, 0.82,
                   ["open-source", "dev-tools", "community"], "2026-05-01",
                   True, True, 2.0, 100000, "weekly", "transcript"),

            # TIER 2 — Thought Leaders
            Source("Paul Graham Essays", "http://paulgraham.com",
                   "http://paulgraham.com/rss.html", "blog",
                   TrustTier.TIER_2, 0.92,
                   ["startups", "philosophy", "advice"], "2026-05-01",
                   True, True, 3.0, 500000, "monthly", "rss"),
            Source("Martin Fowler", "https://martinfowler.com",
                   "https://martinfowler.com/feed.atom", "blog",
                   TrustTier.TIER_2, 0.90,
                   ["architecture", "agile", "patterns"], "2026-05-01",
                   True, True, 4.0, 300000, "monthly", "rss"),

            # TIER 3 — Specialized
            Source("Distill.pub", "https://distill.pub",
                   "https://distill.pub/rss.xml", "research",
                   TrustTier.TIER_3, 0.88,
                   ["ml", "visualization", "research"], "2026-05-01",
                   True, True, 5.0, 100000, "monthly", "rss"),
            Source("OWASP", "https://owasp.org",
                   "https://owasp.org/feed.xml", "blog",
                   TrustTier.TIER_3, 0.85,
                   ["security", "best-practices"], "2026-05-01",
                   True, True, 3.0, 200000, "monthly", "rss"),
        ]

    def export_config(self, path: str):
        """Export verified sources to JSON config."""
        data = {
            "sources": [s.to_dict() for s in self.verified_sources.values()],
            "tier_1_count": sum(1 for s in self.verified_sources.values() 
                               if s.trust_tier == TrustTier.TIER_1),
            "tier_2_count": sum(1 for s in self.verified_sources.values() 
                               if s.trust_tier == TrustTier.TIER_2),
            "tier_3_count": sum(1 for s in self.verified_sources.values() 
                               if s.trust_tier == TrustTier.TIER_3),
            "total_verified": len(self.verified_sources),
            "threshold": self.threshold,
            "exported_at": datetime.now().isoformat(),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return data


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    vetter = SourceVetter(threshold=0.65)
    sources = vetter.load_default_sources()

    passed, failed = 0, 0
    for source in sources:
        ok, reason = vetter.vet_source(source)
        if ok:
            passed += 1
            print(f"✅ {source.name}: {reason}")
        else:
            failed += 1
            print(f"❌ {source.name}: {reason}")

    print(f"
{'='*50}")
    print(f"Total: {passed} passed, {failed} blocked")
    vetter.export_config("./sources_config.json")
    print("Config exported to sources_config.json")
