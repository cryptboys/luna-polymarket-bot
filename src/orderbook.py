# Order Book Intelligence Module
# Phase 4: Depth analysis, whale detection, support/resistance, imbalance scoring

import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OrderBookLevel:
    """Single price level in order book"""
    price: float
    size: float  # in USD
    count: int = 0  # number of orders at this level


@dataclass
class OrderBookAnalysis:
    """Result of order book analysis"""
    market_id: str
    timestamp: float = 0
    
    # Raw levels
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    
    # Derived metrics
    mid_price: float = 0.0
    spread: float = 0.0
    spread_bps: float = 0.0
    
    # Depth metrics (top 10 levels)
    bid_depth_10: float = 0.0  # Total USD in top 10 bid levels
    ask_depth_10: float = 0.0
    total_depth: float = 0.0
    
    # Imbalance
    bid_ask_imbalance: float = 0.0  # -1.0 (heavy ask) to +1.0 (heavy bid)
    imbalance_score: float = 0.0  # 0-1 normalized
    
    # Whale detection
    whale_bids: List[OrderBookLevel] = field(default_factory=list)
    whale_asks: List[OrderBookLevel] = field(default_factory=list)
    whale_presence: bool = False
    whale_side: str = "neutral"  # "bid", "ask", "neutral"
    whale_size_ratio: float = 0.0  # whale size / total depth
    
    # Support/Resistance
    support_level: float = 0.0
    resistance_level: float = 0.0
    support_strength: float = 0.0  # 0-1
    resistance_strength: float = 0.0
    
    # Scoring
    depth_score: float = 0.0  # 0-1: how thick is the book
    liquidity_quality: str = "unknown"  # "excellent", "good", "fair", "poor"
    
    # Price from order book
    best_bid: float = 0.0
    best_ask: float = 0.0


class OrderBookAnalyzer:
    """
    Analyzes Polymarket CLOB order books for trading signals.
    
    Key insights:
    - Whale detection: Large orders indicate smart money positioning
    - Imbalance: Bid-heavy = bullish pressure, ask-heavy = bearish
    - Support/Resistance: Clusters of orders create natural price barriers
    - Depth: Thick book = easier to enter/exit, less slippage
    """
    
    WHALE_THRESHOLD_USD = 5000  # Orders >$5k are whales on Polymarket
    DEPTH_LEVELS = 20  # Analyze top 20 levels each side
    
    def __init__(self, polymarket_client=None):
        self.client = polymarket_client
        self._cached_books: Dict[str, OrderBookAnalysis] = {}
        self._cache_ttl = 30  # seconds
    
    def analyze(self, market_id: str, token_id: str = None) -> Optional[OrderBookAnalysis]:
        """
        Fetch and analyze order book for a market.
        Returns comprehensive analysis or None if unavailable.
        """
        # Check cache
        cached = self._cached_books.get(market_id)
        if cached and (time.time() - cached.timestamp) < self._cache_ttl:
            return cached
        
        # Fetch order book
        try:
            if self.client and self.client.is_connected():
                book_data = self.client.get_orderbook(token_id or market_id)
            else:
                # Mock for paper testing
                book_data = self._generate_mock_book(market_id)
            
            if not book_data:
                return None
            
            analysis = self._parse_and_analyze(market_id, book_data)
            
            if analysis:
                self._cached_books[market_id] = analysis
            
            return analysis
            
        except Exception as e:
            logger.warning(f"Order book analysis failed for {market_id}: {e}")
            return None
    
    def _parse_and_analyze(self, market_id: str, book_data: Dict) -> OrderBookAnalysis:
        """Parse raw order book data and compute all metrics"""
        analysis = OrderBookAnalysis(market_id=market_id, timestamp=time.time())
        
        # Parse bids and asks
        raw_bids = book_data.get('bids', [])
        raw_asks = book_data.get('asks', [])
        
        analysis.bids = [
            OrderBookLevel(price=float(b.get('price', 0)), size=float(b.get('size', 0)))
            for b in raw_bids[:self.DEPTH_LEVELS]
            if float(b.get('price', 0)) > 0
        ]
        analysis.asks = [
            OrderBookLevel(price=float(a.get('price', 0)), size=float(a.get('size', 0)))
            for a in raw_asks[:self.DEPTH_LEVELS]
            if float(a.get('price', 0)) > 0
        ]
        
        if not analysis.bids or not analysis.asks:
            return analysis
        
        # Sort: bids descending, asks ascending
        analysis.bids.sort(key=lambda x: x.price, reverse=True)
        analysis.asks.sort(key=lambda x: x.price)
        
        # Basic metrics
        analysis.best_bid = analysis.bids[0].price
        analysis.best_ask = analysis.asks[0].price
        analysis.mid_price = (analysis.best_bid + analysis.best_ask) / 2
        analysis.spread = analysis.best_ask - analysis.best_bid
        analysis.spread_bps = (analysis.spread / analysis.mid_price * 10000) if analysis.mid_price > 0 else 0
        
        # Depth calculations
        analysis.bid_depth_10 = sum(b.size for b in analysis.bids[:10])
        analysis.ask_depth_10 = sum(a.size for a in analysis.asks[:10])
        analysis.total_depth = analysis.bid_depth_10 + analysis.ask_depth_10
        
        # Imbalance
        if analysis.total_depth > 0:
            analysis.bid_ask_imbalance = (analysis.bid_depth_10 - analysis.ask_depth_10) / analysis.total_depth
            # Normalize to 0-1 scale
            analysis.imbalance_score = abs(analysis.bid_ask_imbalance)
        
        # Whale detection
        self._detect_whales(analysis)
        
        # Support/Resistance
        self._find_support_resistance(analysis)
        
        # Depth score
        self._calculate_depth_score(analysis)
        
        # Liquidity quality classification
        self._classify_liquidity(analysis)
        
        return analysis
    
    def _detect_whales(self, analysis: OrderBookAnalysis):
        """Detect large orders (whales) in the order book"""
        analysis.whale_bids = [b for b in analysis.bids if b.size >= self.WHALE_THRESHOLD_USD]
        analysis.whale_asks = [a for a in analysis.asks if a.size >= self.WHALE_THRESHOLD_USD]
        
        analysis.whale_presence = bool(analysis.whale_bids or analysis.whale_asks)
        
        whale_bid_size = sum(w.size for w in analysis.whale_bids)
        whale_ask_size = sum(w.size for w in analysis.whale_asks)
        total_whale = whale_bid_size + whale_ask_size
        
        if total_whale > 0:
            analysis.whale_size_ratio = total_whale / max(analysis.total_depth, 1)
            if whale_bid_size > whale_ask_size * 1.5:
                analysis.whale_side = "bid"
            elif whale_ask_size > whale_bid_size * 1.5:
                analysis.whale_side = "ask"
            else:
                analysis.whale_side = "neutral"
    
    def _find_support_resistance(self, analysis: OrderBookAnalysis):
        """Identify support and resistance levels from order clusters"""
        if not analysis.bids or not analysis.asks:
            return
        
        # Support: Largest bid level within 5% of mid
        mid = analysis.mid_price
        support_threshold = mid * 0.95
        
        support_candidates = [b for b in analysis.bids if b.price >= support_threshold]
        if support_candidates:
            strongest = max(support_candidates, key=lambda x: x.size)
            analysis.support_level = strongest.price
            max_possible = max(b.size for b in analysis.bids) if analysis.bids else 1
            analysis.support_strength = strongest.size / max(max_possible, 1)
        
        # Resistance: Largest ask level within 5% of mid
        resistance_threshold = mid * 1.05
        
        resistance_candidates = [a for a in analysis.asks if a.price <= resistance_threshold]
        if resistance_candidates:
            strongest = max(resistance_candidates, key=lambda x: x.size)
            analysis.resistance_level = strongest.price
            max_possible = max(a.size for a in analysis.asks) if analysis.asks else 1
            analysis.resistance_strength = strongest.size / max(max_possible, 1)
    
    def _calculate_depth_score(self, analysis: OrderBookAnalysis):
        """Calculate overall depth quality score (0-1)"""
        if analysis.total_depth <= 0:
            analysis.depth_score = 0.0
            return
        
        # Score based on total depth (log scale)
        import math
        depth = analysis.total_depth
        if depth >= 100000:
            base_score = 1.0
        elif depth >= 50000:
            base_score = 0.8
        elif depth >= 20000:
            base_score = 0.6
        elif depth >= 10000:
            base_score = 0.4
        elif depth >= 5000:
            base_score = 0.2
        else:
            base_score = 0.1
        
        # Bonus for balanced book (both sides have depth)
        balance_factor = 1.0
        if analysis.bid_depth_10 > 0 and analysis.ask_depth_10 > 0:
            ratio = min(analysis.bid_depth_10, analysis.ask_depth_10) / max(analysis.bid_depth_10, analysis.ask_depth_10)
            balance_factor = 0.5 + (ratio * 0.5)  # 0.5-1.0
        
        analysis.depth_score = base_score * balance_factor
        analysis.depth_score = max(0.0, min(1.0, analysis.depth_score))
    
    def _classify_liquidity(self, analysis: OrderBookAnalysis):
        """Classify liquidity quality"""
        if analysis.depth_score >= 0.8:
            analysis.liquidity_quality = "excellent"
        elif analysis.depth_score >= 0.6:
            analysis.liquidity_quality = "good"
        elif analysis.depth_score >= 0.3:
            analysis.liquidity_quality = "fair"
        else:
            analysis.liquidity_quality = "poor"
    
    # ═══════════════════════════════════════════
    # TRADING SIGNALS FROM ORDER BOOK
    # ═══════════════════════════════════════════
    
    def get_trading_signals(self, analysis: OrderBookAnalysis) -> Dict[str, Any]:
        """
        Generate trading signals from order book analysis.
        Returns confidence adjustments and recommended actions.
        """
        signals = {
            'confidence_adjustment': 0.0,
            'recommended_action': 'NEUTRAL',
            'reasons': [],
            'risk_level': 'normal',
        }
        
        if not analysis or not analysis.bids:
            signals['reasons'].append("No order book data")
            return signals
        
        # Signal 1: Whale positioning
        if analysis.whale_presence:
            if analysis.whale_side == "bid" and analysis.whale_size_ratio > 0.3:
                signals['confidence_adjustment'] += 0.10
                signals['reasons'].append(f"Whale accumulation: ${sum(w.size for w in analysis.whale_bids):,.0f} on bid side")
            elif analysis.whale_side == "ask" and analysis.whale_size_ratio > 0.3:
                signals['confidence_adjustment'] -= 0.10
                signals['reasons'].append(f"Whale distribution: ${sum(w.size for w in analysis.whale_asks):,.0f} on ask side")
        
        # Signal 2: Imbalance
        if analysis.bid_ask_imbalance > 0.3:
            signals['confidence_adjustment'] += 0.05
            signals['reasons'].append(f"Bid-heavy book: {analysis.bid_ask_imbalance:+.2f} imbalance")
        elif analysis.bid_ask_imbalance < -0.3:
            signals['confidence_adjustment'] -= 0.05
            signals['reasons'].append(f"Ask-heavy book: {analysis.bid_ask_imbalance:+.2f} imbalance")
        
        # Signal 3: Depth quality
        if analysis.liquidity_quality in ('excellent', 'good'):
            signals['confidence_adjustment'] += 0.03
            signals['reasons'].append(f"Good liquidity: {analysis.liquidity_quality}")
        elif analysis.liquidity_quality == 'poor':
            signals['confidence_adjustment'] -= 0.05
            signals['risk_level'] = 'elevated'
            signals['reasons'].append("Poor liquidity — high slippage risk")
        
        # Signal 4: Support/Resistance proximity
        if analysis.support_level > 0 and analysis.mid_price > 0:
            distance_to_support = (analysis.mid_price - analysis.support_level) / analysis.mid_price
            if distance_to_support < 0.02:  # Within 2% of support
                signals['confidence_adjustment'] += 0.05
                signals['reasons'].append(f"Near support: {distance_to_support:.1%} away (strength: {analysis.support_strength:.2f})")
        
        if analysis.resistance_level > 0 and analysis.mid_price > 0:
            distance_to_resistance = (analysis.resistance_level - analysis.mid_price) / analysis.mid_price
            if distance_to_resistance < 0.02:  # Within 2% of resistance
                signals['confidence_adjustment'] -= 0.05
                signals['reasons'].append(f"Near resistance: {distance_to_resistance:.1%} away (strength: {analysis.resistance_strength:.2f})")
        
        # Determine recommended action
        if signals['confidence_adjustment'] > 0.08:
            signals['recommended_action'] = 'BULLISH'
        elif signals['confidence_adjustment'] < -0.08:
            signals['recommended_action'] = 'BEARISH'
        else:
            signals['recommended_action'] = 'NEUTRAL'
        
        return signals
    
    def _generate_mock_book(self, market_id: str) -> Dict:
        """Generate realistic mock order book for testing"""
        import random
        
        # Random mid price between 0.30 and 0.70
        mid = random.uniform(0.30, 0.70)
        spread = random.uniform(0.005, 0.02)  # 0.5% to 2% spread
        
        bids = []
        asks = []
        
        for i in range(self.DEPTH_LEVELS):
            # Bids: below mid, descending price
            bid_price = round(mid - (spread/2) - (i * random.uniform(0.002, 0.01)), 3)
            if bid_price <= 0:
                bid_price = 0.01
            
            # Size: random, with occasional whale
            size = random.uniform(500, 8000)
            if random.random() < 0.1:  # 10% chance of whale
                size = random.uniform(8000, 30000)
            
            bids.append({'price': str(bid_price), 'size': str(size)})
            
            # Asks: above mid, ascending price
            ask_price = round(mid + (spread/2) + (i * random.uniform(0.002, 0.01)), 3)
            if ask_price >= 1:
                ask_price = 0.99
            
            size = random.uniform(500, 8000)
            if random.random() < 0.1:
                size = random.uniform(8000, 30000)
            
            asks.append({'price': str(ask_price), 'size': str(size)})
        
        return {
            'market': market_id,
            'bids': bids,
            'asks': asks,
            'timestamp': time.time(),
        }


class OrderBookTracker:
    """Track order book changes over time for a market"""
    
    def __init__(self, analyzer: OrderBookAnalyzer, max_history: int = 30):
        self.analyzer = analyzer
        self.history: Dict[str, List[OrderBookAnalysis]] = {}
        self.max_history = max_history
    
    def update(self, market_id: str) -> Optional[OrderBookAnalysis]:
        """Update order book for a market and track changes"""
        analysis = self.analyzer.analyze(market_id)
        if not analysis:
            return None
        
        if market_id not in self.history:
            self.history[market_id] = []
        
        self.history[market_id].append(analysis)
        if len(self.history[market_id]) > self.max_history:
            self.history[market_id] = self.history[market_id][-self.max_history:]
        
        return analysis
    
    def get_trend(self, market_id: str) -> str:
        """Determine order book trend from recent history"""
        history = self.history.get(market_id, [])
        if len(history) < 3:
            return 'insufficient_data'
        
        recent = history[-5:]  # Last 5 snapshots
        imbalance_trend = [a.bid_ask_imbalance for a in recent]
        
        # Simple trend detection
        if all(i > 0.2 for i in imbalance_trend):
            return 'bid_dominant'
        elif all(i < -0.2 for i in imbalance_trend):
            return 'ask_dominant'
        elif abs(imbalance_trend[-1] - imbalance_trend[0]) > 0.2:
            return 'shifting'
        else:
            return 'stable'
    
    def get_depth_trend(self, market_id: str) -> float:
        """Get liquidity trend: >0 increasing, <0 decreasing"""
        history = self.history.get(market_id, [])
        if len(history) < 2:
            return 0.0
        
        recent = history[-5:]
        depths = [a.total_depth for a in recent]
        
        if not depths:
            return 0.0
        
        # Simple linear trend
        first_half = sum(depths[:len(depths)//2]) / (len(depths)//2)
        second_half = sum(depths[len(depths)//2:]) / (len(depths) - len(depths)//2)
        
        if first_half > 0:
            return (second_half - first_half) / first_half
        return 0.0
