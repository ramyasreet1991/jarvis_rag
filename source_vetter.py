"""
Jarvis RAG — Source Vetting Engine
Validates authenticity and credibility before ANY content enters the knowledge base.
Runs on CPU (lightweight), blocks bad sources at the gate.
"""
import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
from datetime import datetime
import feedparser


class TrustTier(Enum):
    TIER_1 = "tier_1"      # 0.90–1.0  — Primary trusted
    TIER_2 = "tier_2"      # 0.75–0.90 — Quality community
    TIER_3 = "tier_3"      # 0.65–0.75 — Specialized / curated
    BLOCKED = "blocked"    # <0.65     — Rejected


class SourceType(Enum):
    YOUTUBE = "youtube"
    PODCAST = "podcast"
    NEWS = "news"
    BLOG = "blog"
    RESEARCH = "research"


@dataclass
class Source:
    name: str
    url: str
    feed_url: Optional[str] = None
    source_type: str = "blog"   # matches SourceType values
    trust_tier: TrustTier = TrustTier.TIER_2
    credibility_score: float = 0.75
    categories: List[str] = field(default_factory=list)
    last_verified: str = ""
    author_verified: bool = False
    editorial_process: bool = False
    citation_density: float = 0.0
    subscriber_count: int = 0
    update_frequency: str = "weekly"    # hourly | daily | weekly | biweekly | monthly
    extraction_method: str = "rss"      # rss | api | scrape | transcript

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
    """6-factor credibility scoring engine with blacklist and batch validation."""

    # Credibility factor weights (must sum to 1.0)
    WEIGHTS = {
        "domain_authority":    0.25,
        "author_reputation":   0.25,
        "content_quality":     0.20,
        "citation_density":    0.15,
        "update_freshness":    0.10,
        "community_validation": 0.05,
    }

    # Domain tiers for fast lookup
    TIER_1_DOMAINS = {
        "arxiv.org", "news.ycombinator.com",
        "aws.amazon.com", "cloud.google.com",
        "openai.com", "deepmind.google", "research.google",
        "microsoft.com", "ieee.org", "acm.org",
        "infoq.com", "researchgate.net",
        "scholar.google.com", "github.com",
        "thoughtworks.com",
    }

    TIER_2_DOMAINS = {
        "techcrunch.com", "theverge.com", "wired.com",
        "arstechnica.com", "dev.to", "hashnode.com",
        "hashnode.dev", "medium.com", "substack.com",
        "openai.com/blog", "deepmind.google/blog",
        "anthropic.com/blog",
    }

    TIER_3_PATTERNS = [
        r".*\.dev$",
        r".*\.engineer$",
        r".*\.io$",
    ]

    BLACKLIST_DOMAINS = {
        "content-farm.com",
        "spammy-seo.net",
    }

    def __init__(self, threshold: float = 0.65):
        self.threshold = threshold
        self.verified_sources: Dict[str, Source] = {}
        self.blocked_domains: set = set()
        self.verified_authors: Dict[str, List[str]] = self._load_verified_authors()

    def _load_verified_authors(self) -> Dict[str, List[str]]:
        return {
            "youtube": [
                "ThePrimeagen", "Fireship", "ArjanCodes",
                "System Design Interview", "ByteByteGo",
                "Code Aesthetic", "NetworkChuck",
                "3Blue1Brown", "TechWorld with Nana",
            ],
            "twitter": [
                "sama", "karpathy", "ylecun",
                "torvalds", "gvanrossum", "DHH",
                "paulg",
            ],
            "blog": [
                "paulgraham.com", "martinfowler.com",
                "wait-but-why.com", "ribbonfarm.com",
            ],
            "substack": [
                "jack_krupansky",
            ],
        }

    # ── Scoring ───────────────────────────────────────────────────────────────

    def score_source(self, source: Source) -> Tuple[float, Dict]:
        """Score a source using 6 weighted factors and assign its trust tier."""
        scores = {
            "domain_authority":    self._score_domain_authority(source),
            "author_reputation":   self._score_author_reputation(source),
            "content_quality":     self._score_content_quality(source),
            "citation_density":    min(source.citation_density / 3.0, 1.0),
            "update_freshness":    self._score_freshness(source),
            "community_validation": self._score_community(source),
        }

        total = sum(scores[k] * self.WEIGHTS[k] for k in scores)

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
        domain = source.url.split("/")[2] if "/" in source.url else source.url

        if domain in self.BLACKLIST_DOMAINS or domain in self.blocked_domains:
            return 0.0
        if any(d in domain for d in self.TIER_1_DOMAINS):
            return 1.0
        if any(d in domain for d in self.TIER_2_DOMAINS):
            return 0.85
        for pattern in self.TIER_3_PATTERNS:
            if re.match(pattern, domain):
                return 0.70
        if ".edu" in domain or ".gov" in domain:
            return 0.95
        if source.editorial_process:
            return 0.75
        return 0.60

    def _score_author_reputation(self, source: Source) -> float:
        if source.author_verified:
            return 1.0
        source_key = source.source_type.lower()
        if source_key in self.verified_authors:
            # Check if source name matches a verified author
            for author in self.verified_authors[source_key]:
                if author.lower() in source.name.lower() or author.lower() in source.url.lower():
                    return 1.0
        if source.source_type == "youtube" and source.subscriber_count > 500000:
            return 0.95
        if source.source_type == "youtube" and source.subscriber_count > 100000:
            return 0.85
        if source.source_type == "podcast" and source.subscriber_count > 50000:
            return 0.85
        if source.source_type in ("blog", "news") and source.subscriber_count > 100000:
            return 0.80
        return 0.65

    def _score_content_quality(self, source: Source) -> float:
        score = 0.70
        if source.editorial_process:
            score += 0.15
        if source.citation_density > 1.0:
            score += 0.10
        if source.source_type == "research":
            score += 0.15
        return min(score, 1.0)

    def _score_freshness(self, source: Source) -> float:
        """Score based on update frequency or last-verified date age."""
        if source.last_verified:
            try:
                last = datetime.fromisoformat(source.last_verified)
                days_ago = (datetime.now() - last).days
                if days_ago <= 7:
                    return 1.0
                elif days_ago <= 30:
                    return 0.90
                elif days_ago <= 90:
                    return 0.70
                elif days_ago <= 180:
                    return 0.50
                else:
                    return 0.30
            except ValueError:
                pass
        freq_map = {
            "hourly": 1.0, "daily": 0.95, "weekly": 0.85,
            "biweekly": 0.75, "monthly": 0.65,
        }
        return freq_map.get(source.update_frequency, 0.60)

    def _score_community(self, source: Source) -> float:
        thresholds = {
            "youtube":  50000,
            "podcast":  10000,
            "blog":      1000,
            "news":      5000,
        }
        threshold = thresholds.get(source.source_type, 1000)
        count = source.subscriber_count

        if count >= threshold * 20:
            return 1.0
        if count >= threshold * 10:
            return 0.90
        if count >= threshold * 2:
            return 0.75
        if count >= threshold:
            return 0.60
        if count >= 100:
            return 0.50
        return 0.40

    def _generate_validation_reason(self, scores: Dict, final: float) -> str:
        factors = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_factor = factors[0][0]
        if final >= 0.85:
            return f"High credibility (primary: {top_factor})"
        elif final >= 0.65:
            return f"Credible source (primary: {top_factor})"
        return f"Low credibility (score: {final:.2f}, concern: weak {factors[-1][0]})"

    # ── Vetting Pipeline ──────────────────────────────────────────────────────

    def verify_feed(self, source: Source) -> bool:
        """Check that the RSS/feed URL is reachable and has entries."""
        if not source.feed_url:
            return True
        try:
            feed = feedparser.parse(source.feed_url)
            return len(feed.entries) > 0
        except Exception:
            return False

    def vet_source(self, source: Source) -> Tuple[bool, str]:
        """Full vetting pipeline. Returns (passed, reason)."""
        domain = source.url.split("/")[2] if "/" in source.url else source.url
        if domain in self.BLACKLIST_DOMAINS or domain in self.blocked_domains:
            return False, "Domain on blacklist"

        if source.feed_url and not self.verify_feed(source):
            return False, "Feed inaccessible or empty"

        score, breakdown = self.score_source(source)

        if score < self.threshold:
            return False, f"Credibility score {score:.2f} below threshold {self.threshold}"

        self.verified_sources[source.name] = source
        return True, f"Approved: {source.trust_tier.value} (score: {score:.2f})"

    def batch_validate_sources(self, sources: List[Source]) -> Dict[str, List]:
        """Validate a list of sources; return approved / pending / rejected buckets."""
        approved, pending, rejected = [], [], []

        for source in sources:
            ok, reason = self.vet_source(source)
            result = {"source": source, "score": source.credibility_score, "reason": reason}

            if ok:
                approved.append(result)
            elif source.credibility_score >= 0.50:
                pending.append(result)   # Manual review needed
            else:
                rejected.append(result)

        return {"approved": approved, "pending": pending, "rejected": rejected}

    # ── Default Sources ───────────────────────────────────────────────────────

    def load_default_sources(self) -> List[Source]:
        """Return the pre-vetted 50+ tech source catalogue."""
        return [
            # ── TIER 1 — Enterprise & Research ─────────────────────────────
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
            Source("Anthropic Blog", "https://anthropic.com/blog",
                   "https://anthropic.com/blog/rss", "blog",
                   TrustTier.TIER_1, 0.97,
                   ["ai", "safety", "llm"], "2026-05-01",
                   True, True, 4.0, 200000, "weekly", "rss"),
            Source("InfoQ", "https://www.infoq.com",
                   "https://www.infoq.com/feed/", "news",
                   TrustTier.TIER_1, 0.95,
                   ["architecture", "enterprise", "technology"], "2026-05-01",
                   True, True, 3.0, 100000, "daily", "rss"),

            # ── TIER 1 — YouTube ────────────────────────────────────────────
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
            Source("ArjanCodes", "https://www.youtube.com/@ArjanCodes",
                   "https://www.youtube.com/feeds/videos.xml?channel_id=UCVhQ2NnY5Rskt6UjCUkJ_DA",
                   "youtube", TrustTier.TIER_1, 0.90,
                   ["python", "design-patterns", "architecture"], "2026-05-01",
                   True, False, 1.0, 350000, "weekly", "transcript"),
            Source("ByteByteGo", "https://www.youtube.com/@ByteByteGo",
                   "https://www.youtube.com/feeds/videos.xml?channel_id=UCZgt6AzoyjslHTC9dEH8hLg",
                   "youtube", TrustTier.TIER_1, 0.92,
                   ["system-design", "architecture"], "2026-05-01",
                   True, False, 1.5, 800000, "weekly", "transcript"),
            Source("3Blue1Brown", "https://www.youtube.com/@3blue1brown",
                   "https://www.youtube.com/feeds/videos.xml?channel_id=UCYO_jab_esuFRV4b17AJtAw",
                   "youtube", TrustTier.TIER_1, 0.95,
                   ["math", "ml", "visualization"], "2026-05-01",
                   True, False, 1.0, 5000000, "monthly", "transcript"),

            # ── TIER 2 — Quality Community ──────────────────────────────────
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

            # ── TIER 2 — Podcasts ───────────────────────────────────────────
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
            Source("Kubernetes Podcast", "https://kubernetespodcast.com",
                   "https://kubernetespodcast.com/feeds/audio.xml", "podcast",
                   TrustTier.TIER_2, 0.85,
                   ["kubernetes", "cloud-native", "devops"], "2026-05-01",
                   True, True, 2.0, 50000, "weekly", "transcript"),

            # ── TIER 2 — Thought Leaders ────────────────────────────────────
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
            Source("Julia Evans", "https://jvns.ca",
                   "https://jvns.ca/atom.xml", "blog",
                   TrustTier.TIER_2, 0.88,
                   ["linux", "debugging", "tools"], "2026-05-01",
                   True, True, 3.0, 100000, "monthly", "rss"),

            # ── TIER 3 — Specialized ────────────────────────────────────────
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
            Source("Linux Foundation", "https://www.linuxfoundation.org",
                   "https://www.linuxfoundation.org/feed/", "blog",
                   TrustTier.TIER_3, 0.85,
                   ["linux", "open-source", "cloud-native"], "2026-05-01",
                   True, True, 2.0, 150000, "weekly", "rss"),
        ]

    # ── Export ────────────────────────────────────────────────────────────────

    def export_config(self, path: str) -> Dict:
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


# ── Quick test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    vetter = SourceVetter(threshold=0.65)
    sources = vetter.load_default_sources()

    results = vetter.batch_validate_sources(sources)

    print(f"Approved ({len(results['approved'])}):")
    for r in results["approved"]:
        print(f"  ✅ {r['source'].name}: {r['score']:.2f} — {r['reason']}")

    print(f"\nPending review ({len(results['pending'])}):")
    for r in results["pending"]:
        print(f"  ⏳ {r['source'].name}: {r['score']:.2f} — {r['reason']}")

    print(f"\nRejected ({len(results['rejected'])}):")
    for r in results["rejected"]:
        print(f"  ❌ {r['source'].name}: {r['score']:.2f} — {r['reason']}")

    vetter.export_config("./sources_config.json")
    print("\nConfig exported to sources_config.json")
