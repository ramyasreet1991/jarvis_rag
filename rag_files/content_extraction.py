"""
Content Extraction Module
Extracts content from: YouTube, Podcasts, Blogs, RSS Feeds
"""

import requests
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re


@dataclass
class ExtractedContent:
    """Standardized content format across all sources"""
    source_type: str
    url: str
    title: str
    author: str
    content: str  # Main text/transcript
    summary: Optional[str] = None
    published_date: Optional[datetime] = None
    updated_date: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    
    def get_hash(self) -> str:
        """Generate unique hash for deduplication"""
        import hashlib
        content_str = f"{self.url}_{self.published_date}_{self.title}"
        return hashlib.sha256(content_str.encode()).hexdigest()


class ContentExtractor:
    """Base extractor class"""
    
    def extract(self, url: str) -> Optional[ExtractedContent]:
        raise NotImplementedError


class YouTubeExtractor(ContentExtractor):
    """
    Extract from YouTube videos
    Uses: YouTube Transcript API + metadata
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.transcript_url = "https://www.googleapis.com/youtube/v3"
    
    def extract(self, url: str) -> Optional[ExtractedContent]:
        """Extract YouTube video content and transcript"""
        try:
            video_id = self._extract_video_id(url)
            if not video_id:
                return None
            
            # Get transcript
            transcript_text = self._get_transcript(video_id)
            if not transcript_text:
                # Fallback: Could use Whisper API here
                transcript_text = "[Transcript not available]"
            
            # Get metadata
            metadata = self._get_video_metadata(video_id)
            
            return ExtractedContent(
                source_type="youtube",
                url=url,
                title=metadata.get('title', 'Unknown'),
                author=metadata.get('channel_title', 'Unknown'),
                content=transcript_text,
                summary=metadata.get('description', ''),
                published_date=self._parse_date(metadata.get('published_at')),
                metadata={
                    'video_id': video_id,
                    'channel_id': metadata.get('channel_id'),
                    'view_count': metadata.get('view_count', 0),
                    'like_count': metadata.get('like_count', 0),
                    'duration': metadata.get('duration'),
                    'thumbnail': metadata.get('thumbnail_url'),
                }
            )
        
        except Exception as e:
            print(f"Error extracting YouTube content from {url}: {e}")
            return None
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from various YouTube URL formats"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]+)',
            r'youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def _get_transcript(self, video_id: str) -> Optional[str]:
        """Fetch YouTube transcript"""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            
            # Combine transcript entries
            full_text = ' '.join([entry['text'] for entry in transcript])
            return full_text
        
        except Exception as e:
            print(f"Error fetching transcript for {video_id}: {e}")
            return None
    
    def _get_video_metadata(self, video_id: str) -> Dict:
        """
        Get video metadata (title, channel, view count, etc.)
        In production, use YouTube Data API v3
        """
        # Placeholder: In production, call YouTube API
        # For now, extract from page
        try:
            response = requests.get(f"https://www.youtube.com/watch?v={video_id}", timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract metadata from page
            metadata = {
                'title': soup.find('meta', {'name': 'title'})['content'] if soup.find('meta', {'name': 'title'}) else 'Unknown',
                'description': soup.find('meta', {'name': 'description'})['content'] if soup.find('meta', {'name': 'description'}) else '',
                'channel_title': 'Unknown',  # Would need API
                'view_count': 0,
                'like_count': 0,
                'duration': 'Unknown',
                'thumbnail_url': f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
            }
            
            return metadata
        
        except Exception as e:
            print(f"Error fetching metadata: {e}")
            return {'title': 'Unknown', 'description': ''}
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO format date"""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            return None


class PodcastExtractor(ContentExtractor):
    """
    Extract from podcast RSS feeds + audio transcription
    """
    
    def __init__(self, transcription_service: str = "openai"):
        self.transcription_service = transcription_service
    
    def extract(self, url: str) -> Optional[ExtractedContent]:
        """Extract podcast episode from RSS URL"""
        try:
            feed = feedparser.parse(url)
            
            if not feed.entries:
                return None
            
            # Get latest episode
            entry = feed.entries[0]
            
            # Extract transcript/content
            content = self._extract_episode_content(entry)
            
            # Get audio if available and transcribe
            audio_url = self._find_audio_url(entry)
            if audio_url:
                # In production: transcribe with Whisper/AssemblyAI
                transcript = f"[Audio URL: {audio_url}]\n{content}"
            else:
                transcript = content
            
            return ExtractedContent(
                source_type="podcast",
                url=entry.get('link', url),
                title=entry.get('title', 'Unknown'),
                author=feed.feed.get('author', 'Unknown'),
                content=transcript,
                summary=entry.get('summary', ''),
                published_date=self._parse_rss_date(entry.get('published')),
                metadata={
                    'feed_title': feed.feed.get('title', ''),
                    'feed_url': url,
                    'episode_number': entry.get('episode', ''),
                    'duration': entry.get('duration', ''),
                    'audio_url': audio_url,
                }
            )
        
        except Exception as e:
            print(f"Error extracting podcast from {url}: {e}")
            return None
    
    def _extract_episode_content(self, entry: Dict) -> str:
        """Extract content from podcast entry"""
        # Try multiple sources
        content_sources = [
            entry.get('summary', ''),
            entry.get('content', [{}])[0].get('value', ''),
            entry.get('description', ''),
        ]
        
        return next((s for s in content_sources if s), "")
    
    def _find_audio_url(self, entry: Dict) -> Optional[str]:
        """Find audio file URL in entry"""
        for link in entry.get('links', []):
            if link.get('type', '').startswith('audio/'):
                return link.get('href')
        
        return None
    
    def _parse_rss_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse RFC 2822 date from RSS"""
        if not date_str:
            return None
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except:
            return None


class BlogExtractor(ContentExtractor):
    """
    Extract from blog posts and articles
    """
    
    def extract(self, url: str) -> Optional[ExtractedContent]:
        """Extract blog article content"""
        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract metadata
            title = self._extract_title(soup)
            author = self._extract_author(soup)
            published_date = self._extract_publish_date(soup)
            
            # Extract main content
            content = self._extract_main_content(soup)
            
            # Extract tags
            tags = self._extract_tags(soup)
            
            return ExtractedContent(
                source_type="blog",
                url=url,
                title=title,
                author=author,
                content=content,
                published_date=published_date,
                tags=tags,
                metadata={
                    'domain': urlparse(url).netloc,
                    'canonical_url': self._extract_canonical_url(soup),
                }
            )
        
        except Exception as e:
            print(f"Error extracting blog from {url}: {e}")
            return None
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract article title"""
        # Try multiple sources
        candidates = [
            soup.find('h1'),
            soup.find('meta', {'property': 'og:title'}),
            soup.find('meta', {'name': 'title'}),
            soup.find('title'),
        ]
        
        for candidate in candidates:
            if candidate:
                if hasattr(candidate, 'string'):
                    return candidate.string.strip()
                elif candidate.get('content'):
                    return candidate['content'].strip()
        
        return "Unknown"
    
    def _extract_author(self, soup: BeautifulSoup) -> str:
        """Extract author name"""
        candidates = [
            soup.find('meta', {'name': 'author'}),
            soup.find('meta', {'property': 'article:author'}),
            soup.find(class_=re.compile(r'author', re.I)),
        ]
        
        for candidate in candidates:
            if candidate:
                if candidate.get('content'):
                    return candidate['content'].strip()
                elif candidate.string:
                    return candidate.string.strip()
        
        return "Unknown"
    
    def _extract_publish_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract publication date"""
        date_candidates = [
            soup.find('meta', {'property': 'article:published_time'}),
            soup.find('meta', {'name': 'publish_date'}),
            soup.find('time'),
        ]
        
        for candidate in date_candidates:
            if candidate:
                date_str = candidate.get('content') or candidate.get('datetime')
                if date_str:
                    try:
                        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    except:
                        pass
        
        return None
    
    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """Extract main article text"""
        # Remove script, style, nav, etc.
        for tag in soup(['script', 'style', 'nav', 'footer', 'button']):
            tag.decompose()
        
        # Try to find main content
        content_selectors = [
            soup.find('article'),
            soup.find(class_=re.compile(r'post-content|article-content|entry-content', re.I)),
            soup.find(id=re.compile(r'content|post|article', re.I)),
            soup.find('main'),
        ]
        
        content_elem = None
        for selector in content_selectors:
            if selector:
                content_elem = selector
                break
        
        if not content_elem:
            content_elem = soup.body or soup.html
        
        return content_elem.get_text(separator='\n', strip=True) if content_elem else ""
    
    def _extract_tags(self, soup: BeautifulSoup) -> List[str]:
        """Extract article tags/categories"""
        tags = []
        
        # Look for tag links
        for link in soup.find_all('a', class_=re.compile(r'tag|category', re.I)):
            text = link.get_text(strip=True)
            if text:
                tags.append(text)
        
        # Meta keywords
        keywords_meta = soup.find('meta', {'name': 'keywords'})
        if keywords_meta:
            keywords = keywords_meta.get('content', '').split(',')
            tags.extend([k.strip() for k in keywords if k.strip()])
        
        return list(set(tags))[:10]  # Return unique tags, max 10
    
    def _extract_canonical_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract canonical URL"""
        canonical = soup.find('link', {'rel': 'canonical'})
        if canonical:
            return canonical.get('href')
        return None


class RSSFeedExtractor(ContentExtractor):
    """
    Extract from generic RSS/Atom feeds
    """
    
    def __init__(self):
        self.blog_extractor = BlogExtractor()
    
    def extract_feed(self, feed_url: str) -> List[ExtractedContent]:
        """Extract all entries from RSS feed"""
        try:
            feed = feedparser.parse(feed_url)
            
            contents = []
            for entry in feed.entries[:20]:  # Limit to 20 entries
                url = entry.get('link')
                if not url:
                    continue
                
                # Try to extract full content
                extracted = self.blog_extractor.extract(url)
                
                if not extracted:
                    # Fallback: use RSS content
                    extracted = ExtractedContent(
                        source_type="rss",
                        url=url,
                        title=entry.get('title', 'Unknown'),
                        author=feed.feed.get('author', 'Unknown'),
                        content=entry.get('summary', entry.get('description', '')),
                        published_date=self._parse_rss_date(entry.get('published')),
                        metadata={
                            'feed_title': feed.feed.get('title', ''),
                            'feed_url': feed_url,
                        }
                    )
                
                contents.append(extracted)
            
            return contents
        
        except Exception as e:
            print(f"Error extracting RSS feed from {feed_url}: {e}")
            return []
    
    def _parse_rss_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except:
            return None


class MultiSourceExtractor:
    """
    Orchestrate extraction from multiple sources
    """
    
    def __init__(self):
        self.youtube = YouTubeExtractor()
        self.podcast = PodcastExtractor()
        self.blog = BlogExtractor()
        self.rss = RSSFeedExtractor()
    
    def extract(self, url: str) -> Optional[ExtractedContent]:
        """Auto-detect source type and extract"""
        
        # YouTube detection
        if 'youtube.com' in url or 'youtu.be' in url:
            return self.youtube.extract(url)
        
        # Podcast RSS detection
        if 'podcast' in url.lower() or url.endswith('.xml'):
            # Try as podcast feed
            extracted = self.podcast.extract(url)
            if extracted:
                return extracted
        
        # Default: treat as blog/article
        return self.blog.extract(url)


# Example usage
if __name__ == "__main__":
    extractor = MultiSourceExtractor()
    
    # Test URLs
    test_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://example.com/blog-post",
    ]
    
    for url in test_urls:
        content = extractor.extract(url)
        if content:
            print(f"\n✅ {content.title}")
            print(f"   Author: {content.author}")
            print(f"   Source: {content.source_type}")
            print(f"   Content length: {len(content.content)} chars")
        else:
            print(f"\n❌ Failed to extract: {url}")
