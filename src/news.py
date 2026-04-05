# Real-Time News Sentiment Module
# Phase 5.2: Scrape RSS feeds for breaking news, analyze sentiment, adjust probability.
# Cost: $0 (using standard RSS feeds). No LLM involved.

import os
import logging
import requests
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# RSS FEED SOURCES PER CATEGORY
RSS_FEEDS = {
    'crypto': [
        'https://cointelegraph.com/rss',
        'https://coindesk.com/arc/outboundfeeds/rss/',
    ],
    'politics': [
        'https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml',
        'https://feeds.nbcnews.com/nbcnews/public/politics',
        'https://www.politico.com/rss/politicopicks.xml',
    ],
    'sports': [
        'https://www.espn.com/espn/rss/news',
    ],
    'business': [
        'https://feeds.bloomberg.com/markets/news.rss',
        'https://www.cnbc.com/id/10001147/device/rss/rss.html',
    ],
    'science': [
        'https://rss.nytimes.com/services/xml/rss/nyt/Science.xml',
    ],
    'default': [
        'https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml',
    ]
}

# KEYWORD SENTIMENT DICTIONARIES (Lightweight)
POSITIVE_WORDS = {
    'approve', 'win', 'won', 'success', 'bullish', 'growth', 'high', 'record', 
    'support', 'adopt', 'adoption', 'gain', 'profit', 'agree', 'deal', 'breakthrough',
    'positive', 'beat', 'exceed', 'soar', 'rally', 'surge', 'boom', 'up', 'upbeat',
    'optimistic', 'confidence', 'strong', 'stable', 'recover', 'recovery', 'boost', 'favorable'
}

NEGATIVE_WORDS = {
    'lose', 'lost', 'fail', 'failed', 'bearish', 'crash', 'low', 'sanction', 'ban',
    'reject', 'denied', 'fear', 'risk', 'delay', 'cancel', 'cancel', 'drop', 'fall',
    'plunge', 'slump', 'down', 'negative', 'pessimistic', 'weak', 'volatile', 'fraud',
    'hack', 'scam', 'investigation', 'probe', 'lawsuit', 'fine', 'penalty', 'loss'
}

# CATEGORY KEYWORD MAPPING
CATEGORY_KEYWORDS = {
    'crypto': ['crypto', 'bitcoin', 'btc', 'ethereum', 'eth', 'defi', 'solana', 'coin'],
    'politics': ['election', 'vote', 'congress', 'senate', 'policy', 'law', 'government', 'party'],
    'sports': ['game', 'team', 'player', 'match', 'win', 'cup', 'league', 'finals'],
    'business': ['market', 'stock', 'economy', 'gdp', 'fed', 'rate', 'inflation', 'corp'],
    'science': ['study', 'research', 'discovery', 'health', 'space', 'science', 'tech'],
}


class NewsAnalyzer:
    """
    Fetches news via RSS and calculates sentiment score for specific markets.
    Returns adjustment value:
    +0.05 (Very Bullish News)
    -0.05 (Very Bearish News)
    """
    
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        
    def analyze_market(self, market_name: str, category: str) -> float:
        """
        Get sentiment adjustment for a market.
        Returns float between -0.05 and +0.05.
        """
        # Normalize inputs
        name_lower = market_name.lower()
        cat = category.lower()
        
        # 1. Fetch headlines for category
        headlines = self._fetch_headlines(cat)
        
        # 2. Filter relevant headlines (match keywords)
        relevant = self._filter_relevant(headlines, name_lower, cat)
        
        if not relevant:
            return 0.0
        
        # 3. Calculate sentiment
        total_score = 0.0
        for text in relevant:
            total_score += self._score_sentiment(text)
            
        avg_score = total_score / len(relevant)
        
        # 4. Scale to small adjustment (-0.05 to +0.05)
        # 1.0 sentiment -> +0.05 adjustment
        adjustment = max(-0.05, min(0.05, avg_score * 0.05))
        
        if abs(adjustment) > 0.005:
            logger.info(f"📰 News Sentiment ({cat}): {adjustment:+.4f} | Headlines: {len(relevant)}")
            
        return adjustment

    def _fetch_headlines(self, category: str) -> List[str]:
        """Fetch and cache RSS headlines"""
        cache_key = f"{category}_{datetime.now().minute // 5}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        feeds = RSS_FEEDS.get(category, RSS_FEEDS['default'])
        all_text = []
        
        for feed_url in feeds:
            try:
                resp = requests.get(feed_url, timeout=10)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    for item in root.iter('item'):
                        title = item.find('title')
                        if title is not None and title.text:
                            desc = item.find('description')
                            desc_text = desc.text if desc is not None else ""
                            all_text.append(f"{title.text} {desc_text}")
            except Exception as e:
                logger.debug(f"RSS fetch failed for {feed_url}: {e}")
        
        self._cache[cache_key] = all_text[:50]  # Keep last 50 items per category
        return self._cache[cache_key]

    def _filter_relevant(self, headlines: List[str], market_name: str, category: str) -> List[str]:
        """Keep only headlines that mention market keywords"""
        relevant = []
        
        # Get category keywords
        keywords = set(CATEGORY_KEYWORDS.get(category, []))
        
        # Add words from market name (e.g. "Trump wins" -> "trump")
        market_words = set(market_name.split())
        keywords.update(market_words)
        
        # Remove short words
        keywords = {w for w in keywords if len(w) > 3}
        
        for text in headlines:
            text_lower = text.lower()
            # Check if any keyword appears
            if any(kw in text_lower for kw in keywords):
                relevant.append(text_lower)
        
        return relevant

    def _score_sentiment(self, text: str) -> float:
        """Simple rule-based sentiment: -1.0 to 1.0"""
        words = set(text.split())
        pos_count = len(words.intersection(POSITIVE_WORDS))
        neg_count = len(words.intersection(NEGATIVE_WORDS))
        
        total = pos_count + neg_count
        if total == 0:
            return 0.0
            
        return (pos_count - neg_count) / total
