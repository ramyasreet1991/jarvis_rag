"""
Source Validation & Credibility Scoring Module
Technology Content RAG System
"""

import hashlib
import re
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import requests
from bs4 import BeautifulSoup


class SourceType(Enum):
    YOUTUBE = "youtube"
    PODCAST = "podcast"
    NEWS = "news"
    BLOG = "blog"
    RESEARCH = "research"


@dataclass
class SourceMetadata:
    """Source information and validation"""
    url: str
    source_type: SourceType
    domain: str
    author: str
    name: str
    subscribers_followers: int = 0
    last_checked: datetime = field(default_factory=datetime.now)
    is_verified: bool = False
    credibility_score: float = 0.0
    tags: List[str] = field(default_factory=list)
    notes: str = ""


class SourceValidator:
    """
    Validates and scores sources for authenticity and reliability
    """
    
    # Tier 1: Highest credibility (auto-approve)
    TIER_1_DOMAINS = {
        'hackernews.com', 'news.ycombinator.com',
        'thoughtworks.com/en/radar',
        'infoq.com',
        'arxiv.org',
        'researchgate.net',
        'scholar.google.com',
        'acm.org',
        'ieee.org',
        'github.com',  # With verified author
    }
    
    # Tier 2: High credibility (manual verification)
    TIER_2_DOMAINS = {
        'techcrunch.com',
        'arstechnica.com',
        'theverge.com',
        'medium.com',
        'dev.to',
        'hashnode.com',
        'substack.com',
        'openai.com/blog',
        'deepmind.google/blog',
        'anthropic.com/blog',
    }
    
    # Tier 3: Moderate (requires author verification)
    TIER_3_PATTERNS = [
        r'.*\.dev$',
        r'.*\.engineer$',
        r'.*\.io$',
    ]
    
    # Blacklist: Never ingest
    BLACKLIST_DOMAINS = {
        'content-farm.com',
        'spammy-seo.net',
    }
    
    # Credibility factor weights
    WEIGHTS = {
        'domain_authority': 0.25,
        'author_reputation': 0.25,
        'content_quality': 0.20,
        'citation_density': 0.15,
        'update_freshness': 0.10,
        'community_validation': 0.05,
    }
    
    MIN_CREDIBILITY_THRESHOLD = 0.65
    
    def __init__(self):
        self.verified_authors = self._load_verified_authors()
        self.source_cache: Dict[str, SourceMetadata] = {}
    
    def _load_verified_authors(self) -> Dict[str, List[str]]:
        """
        Load verified technical authors and their channels
        In production, pull from database or API
        """
        return {
            'youtube': [
                'ThePrimeagen',
                'Fireship',
                'ArjanCodes',
                'System Design Interview',
                'ByteByteGo',
                'Code Aesthetic',
                'NetworkChuck',
            ],
            'twitter': [
                'sama', 'karpathy', 'ylecun',
                'torvalds', 'gvanrossum', 'DHH',
                'paulg', 'aandahl'
            ],
            'substack': [
                'jack_krupansky',
                'newsletter_writers_verified'
            ],
            'blog': [
                'paulgraham.com',
                'wait-but-why.com',
                'ribbonfarm.com',
            ]
        }
    
    def validate_source(self, source: SourceMetadata) -> Tuple[bool, float, str]:
        """
        Validate source and return (is_valid, credibility_score, reason)
        """
        # Check blacklist
        if source.domain in self.BLACKLIST_DOMAINS:
            return False, 0.0, "Domain on blacklist"
        
        # Calculate credibility score
        score_breakdown = self._calculate_credibility_score(source)
        final_score = sum(
            score_breakdown[factor] * self.WEIGHTS[factor]
            for factor in self.WEIGHTS.keys()
        )
        
        source.credibility_score = final_score
        
        is_valid = final_score >= self.MIN_CREDIBILITY_THRESHOLD
        reason = self._generate_validation_reason(score_breakdown, final_score)
        
        return is_valid, final_score, reason
    
    def _calculate_credibility_score(self, source: SourceMetadata) -> Dict[str, float]:
        """
        Calculate individual credibility factors (0-1 scale)
        """
        
        # 1. Domain Authority (0-1)
        domain_authority = self._score_domain_authority(source.domain)
        
        # 2. Author Reputation (0-1)
        author_reputation = self._score_author_reputation(source.author, source.source_type)
        
        # 3. Content Quality (requires URL fetch)
        content_quality = self._score_content_quality(source.url) if source.url else 0.5
        
        # 4. Citation Density
        citation_density = self._score_citation_density(source.url) if source.url else 0.4
        
        # 5. Update Freshness (0-1, higher for recent updates)
        update_freshness = self._score_update_freshness(source.last_checked)
        
        # 6. Community Validation
        community_score = self._score_community_validation(
            source.subscribers_followers,
            source.source_type
        )
        
        return {
            'domain_authority': domain_authority,
            'author_reputation': author_reputation,
            'content_quality': content_quality,
            'citation_density': citation_density,
            'update_freshness': update_freshness,
            'community_validation': community_score,
        }
    
    def _score_domain_authority(self, domain: str) -> float:
        """Score domain based on tier and history"""
        if domain in self.TIER_1_DOMAINS:
            return 1.0
        
        if domain in self.TIER_2_DOMAINS:
            return 0.85
        
        # Check against patterns
        for pattern in self.TIER_3_PATTERNS:
            if re.match(pattern, domain):
                return 0.70
        
        # Default: moderate authority
        return 0.60
    
    def _score_author_reputation(self, author: str, source_type: SourceType) -> float:
        """Score author based on verification status"""
        if not author:
            return 0.3
        
        # Check against verified authors
        source_key = source_type.value.lower()
        if source_key in self.verified_authors:
            if author in self.verified_authors[source_key]:
                return 1.0
        
        # In production: Check GitHub stars, publication history, etc.
        # For now, conservative score
        return 0.5
    
    def _score_content_quality(self, url: str) -> float:
        """
        Evaluate content quality: grammar, structure, depth
        """
        try:
            response = requests.get(url, timeout=5)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract text
            text = soup.get_text()
            word_count = len(text.split())
            
            # Heuristics
            quality_score = 0.5
            
            # Minimum depth
            if word_count > 500:
                quality_score += 0.2
            if word_count > 2000:
                quality_score += 0.15
            
            # Presence of code blocks (tech content)
            if soup.find_all('code') or soup.find_all('pre'):
                quality_score += 0.15
            
            # Presence of images/diagrams
            if soup.find_all('img'):
                quality_score += 0.1
            
            return min(quality_score, 1.0)
        
        except Exception as e:
            print(f"Error scoring content quality for {url}: {e}")
            return 0.5
    
    def _score_citation_density(self, url: str) -> float:
        """Higher citation density = higher score"""
        try:
            response = requests.get(url, timeout=5)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Count links
            total_links = len(soup.find_all('a'))
            text = soup.get_text()
            paragraphs = len([p for p in text.split('\n') if len(p.strip()) > 50])
            
            # Links per paragraph ratio
            if paragraphs == 0:
                return 0.4
            
            citation_ratio = total_links / paragraphs
            
            # Optimal: 1-3 links per paragraph
            if citation_ratio > 0.5:
                return 0.9
            elif citation_ratio > 0.2:
                return 0.7
            else:
                return 0.4
        
        except:
            return 0.5
    
    def _score_update_freshness(self, last_checked: datetime) -> float:
        """
        Score based on how recently the source was updated
        Decay factor: older sources score lower
        """
        days_ago = (datetime.now() - last_checked).days
        
        # Freshness windows
        if days_ago <= 7:
            return 1.0
        elif days_ago <= 30:
            return 0.9
        elif days_ago <= 90:
            return 0.7
        elif days_ago <= 180:
            return 0.5
        else:
            return 0.3
    
    def _score_community_validation(self, followers: int, source_type: SourceType) -> float:
        """
        Score based on community support (followers, subscribers, upvotes)
        """
        if followers == 0:
            return 0.5
        
        # Minimum thresholds by source type
        thresholds = {
            SourceType.YOUTUBE: 50000,      # 50k+ subscribers
            SourceType.PODCAST: 10000,      # 10k+ listeners
            SourceType.BLOG: 1000,          # 1k+ followers/subscribers
            SourceType.TWITTER: 5000,       # 5k+ followers
        }
        
        threshold = thresholds.get(source_type, 1000)
        
        if followers >= threshold * 2:
            return 1.0
        elif followers >= threshold:
            return 0.85
        elif followers >= threshold * 0.5:
            return 0.7
        elif followers >= 100:
            return 0.5
        else:
            return 0.3
    
    def _generate_validation_reason(self, scores: Dict, final: float) -> str:
        """Generate human-readable validation summary"""
        factors = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_factor = factors[0][0]
        
        if final >= 0.85:
            return f"High credibility (primary: {top_factor})"
        elif final >= 0.65:
            return f"Credible source (primary: {top_factor})"
        else:
            return f"Low credibility (score: {final:.2f}, concern: weak {factors[-1][0]})"
    
    def batch_validate_sources(self, sources: List[SourceMetadata]) -> Dict[str, List]:
        """
        Validate multiple sources, return organized results
        """
        approved = []
        rejected = []
        pending = []
        
        for source in sources:
            is_valid, score, reason = self.validate_source(source)
            
            result = {
                'source': source,
                'score': score,
                'reason': reason
            }
            
            if is_valid:
                approved.append(result)
            elif score >= 0.5:
                pending.append(result)  # Manual review needed
            else:
                rejected.append(result)
        
        return {
            'approved': approved,
            'pending': pending,
            'rejected': rejected,
        }


# Example usage
if __name__ == "__main__":
    validator = SourceValidator()
    
    # Test sources
    test_sources = [
        SourceMetadata(
            url="https://news.ycombinator.com/item?id=123",
            source_type=SourceType.NEWS,
            domain="hackernews.com",
            author="pg",
            name="Hacker News",
            subscribers_followers=500000,
            last_checked=datetime.now()
        ),
        SourceMetadata(
            url="https://www.youtube.com/@ThePrimeagen/videos",
            source_type=SourceType.YOUTUBE,
            domain="youtube.com",
            author="ThePrimeagen",
            name="ThePrimeagen",
            subscribers_followers=200000,
            last_checked=datetime.now()
        ),
    ]
    
    results = validator.batch_validate_sources(test_sources)
    
    print("✅ APPROVED:")
    for r in results['approved']:
        print(f"  {r['source'].name}: {r['score']:.2f}")
    
    print("\n⏳ PENDING REVIEW:")
    for r in results['pending']:
        print(f"  {r['source'].name}: {r['score']:.2f}")
    
    print("\n❌ REJECTED:")
    for r in results['rejected']:
        print(f"  {r['source'].name}: {r['score']:.2f}")
