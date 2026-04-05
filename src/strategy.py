# Luna's Advanced Trading Strategy Module
# Multi-Factor Scoring, Kelly Criterion, Smart Filters, Dynamic Phase
# Phase 2: Modernize - Intelligent market analysis with adaptive risk

import logging
import math
from datetime import datetime
from typing import Tuple, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# MARKET CATEGORY PROFILES
# ═══════════════════════════════════════════
CATEGORY_PROFILES = {
    # High volatility, high reward — needs more data
    'crypto':       {'vol': 'high',   'base_conf': 0.55, 'risk_adj': -0.05, 'edge_type': 'momentum'},
    'politics':     {'vol': 'medium', 'base_conf': 0.60, 'risk_adj':  0.00, 'edge_type': 'event_driven'},
    'sports':       {'vol': 'medium', 'base_conf': 0.65, 'risk_adj':  0.02, 'edge_type': 'statistical'},
    'science':      {'vol': 'low',    'base_conf': 0.70, 'risk_adj':  0.05, 'edge_type': 'fundamental'},
    'entertainment':{'vol': 'low',    'base_conf': 0.65, 'risk_adj':  0.03, 'edge_type': 'sentiment'},
    'geopolitics':  {'vol': 'high',   'base_conf': 0.50, 'risk_adj': -0.03, 'edge_type': 'event_driven'},
    'business':     {'vol': 'medium', 'base_conf': 0.60, 'risk_adj':  0.00, 'edge_type': 'fundamental'},
    'tech':         {'vol': 'high',   'base_conf': 0.55, 'risk_adj': -0.02, 'edge_type': 'fundamental'},
    'weather':      {'vol': 'low',    'base_conf': 0.75, 'risk_adj':  0.05, 'edge_type': 'statistical'},
    'default':      {'vol': 'medium', 'base_conf': 0.55, 'risk_adj':  0.00, 'edge_type': 'unknown'},
}


@dataclass
class MarketScore:
    """Detailed scoring breakdown for transparency"""
    market_id: str
    market_name: str
    
    # Component scores (0-1 each)
    liquidity_score: float = 0.0
    volume_score: float = 0.0
    spread_score: float = 0.0
    momentum_score: float = 0.0
    price_position_score: float = 0.0
    time_decay_score: float = 0.0
    category_score: float = 0.0
    market_age_score: float = 0.0
    
    # Weighted final
    total_score: float = 0.0
    
    # Recommendation
    action: str = "HOLD"
    recommended_side: str = "YES"
    kelly_fraction: float = 0.0
    reason: str = ""
    
    # Metadata
    timestamp: str = ""
    category: str = "unknown"


class LunaStrategy:
    """
    Luna's Advanced Trading Strategy — Phase 2
    Multi-factor scoring + Kelly Criterion + Smart Filters
    
    Scoring system:
    ┌─────────────────────────────────────────┐
    │ Factor           │ Weight │ Description │
    ├─────────────────────────────────────────┤
    │ Liquidity        │  15%   │ Depth + stability │
    │ Volume           │  15%   │ Activity + trend  │
    │ Spread           │  10%   │ Execution cost    │
    │ Momentum         │  20%   │ Price direction   │
    │ Price Position   │  10%   │ Fair value region │
    │ Time Decay       │  10%   │ Resolution proximity │
    │ Category         │  10%   │ Category edge     │
    │ Market Age       │  10%   │ Maturity          │
    └─────────────────────────────────────────┘
    """
    
    # Component weights
    WEIGHTS = {
        'liquidity':          0.15,
        'volume':             0.15,
        'spread':             0.10,
        'momentum':           0.20,
        'price_position':     0.10,
        'time_decay':         0.10,
        'category':           0.10,
        'market_age':         0.10,
    }
    
    def __init__(self, phase: int = 1):
        self.phase = phase
        self.min_liquidity = 10000
        self.max_daily_loss_pct = 0.20
        self._trade_log = []
    
    def analyze_market(self, market_data: Dict[str, Any], memory: Dict = None) -> Tuple[str, float, str]:
        """
        Main analysis function — multi-factor scoring.
        
        Returns:
            (action, confidence, reason)
        """
        score = self._calculate_full_score(market_data, memory)
        
        # Phase-based threshold
        threshold = self._get_phase_threshold()
        
        # Determine action
        if score.total_score >= threshold:
            action = 'BUY'
        elif score.total_score <= 0.30:  # Very low = contrarian SELL
            action = 'SELL'
        else:
            action = 'HOLD'
        
        # Calculate Kelly fraction for position sizing
        kelly = self._kelly_criterion(score.total_score, market_data.get('best_ask', 0.5))
        score.kelly_fraction = kelly
        
        return action, score.total_score, score.reason
    
    def _calculate_full_score(self, data: Dict, memory: Dict = None) -> MarketScore:
        """Calculate all component scores and combine"""
        
        best_bid = data.get('best_bid', 0)
        best_ask = data.get('best_ask', 1)
        mid_price = (best_bid + best_ask) / 2
        
        score = MarketScore(
            market_id=data.get('id', ''),
            market_name=data.get('name', 'Unknown'),
            category=data.get('category', 'unknown'),
            timestamp=datetime.now().isoformat(),
        )
        
        # 1. LIQUIDITY (15%)
        score.liquidity_score = self._score_liquidity(data.get('liquidity', 0))
        
        # 2. VOLUME (15%)
        score.volume_score = self._score_volume(
            data.get('volume_24h', 0),
            data.get('volume_trend', 'neutral')
        )
        
        # 3. SPREAD (10%)
        score.spread_score = self._score_spread(best_bid, best_ask)
        
        # 4. MOMENTUM (20%)
        score.momentum_score = self._score_momentum(
            data.get('price_change_24h', 0),
            data.get('volume_trend', 'neutral'),
            mid_price
        )
        
        # 5. PRICE POSITION (10%)
        score.price_position_score = self._score_price_position(mid_price)
        
        # 6. TIME DECAY (10%)
        score.time_decay_score = self._score_time_decay(
            data.get('days_to_resolution', 30),
            data.get('market_age_days', 0)
        )
        
        # 7. CATEGORY (10%)
        score.category_score = self._score_category(data.get('category', 'unknown'))
        
        # 8. MARKET AGE (10%)
        score.market_age_score = self._score_market_age(data.get('market_age_days', 0))
        
        # Weighted total
        weighted = (
            score.liquidity_score * self.WEIGHTS['liquidity'] +
            score.volume_score * self.WEIGHTS['volume'] +
            score.spread_score * self.WEIGHTS['spread'] +
            score.momentum_score * self.WEIGHTS['momentum'] +
            score.price_position_score * self.WEIGHTS['price_position'] +
            score.time_decay_score * self.WEIGHTS['time_decay'] +
            score.category_score * self.WEIGHTS['category'] +
            score.market_age_score * self.WEIGHTS['market_age']
        )
        
        score.total_score = max(0.0, min(1.0, weighted))
        
        # Memory adjustment
        if memory:
            memory_adj = self._memory_adjustment(data.get('id', ''), memory)
            score.total_score = max(0.0, min(1.0, score.total_score + memory_adj))
        
        # Determine smart filter result
        filtered = self._smart_filter(score)
        if filtered:
            return filtered
        
        # Determine recommended side
        score.recommended_side = 'YES' if mid_price >= 0.5 else 'NO'
        
        # Generate detailed reason
        score.reason = self._generate_detailed_reason(score, data)
        
        return score
    
    # ═══════════════════════════════════════════
    # SCORING FUNCTIONS
    # ═══════════════════════════════════════════
    
    def _score_liquidity(self, liquidity: float) -> float:
        """
        Liquidity score: higher = better execution, less slippage.
        Scale: $10k → 0.3, $50k → 0.6, $100k+ → 1.0
        """
        if liquidity <= 0:
            return 0.0
        if liquidity >= 100000:
            return 1.0
        # Logarithmic scale
        import math
        return max(0.0, min(1.0, math.log10(liquidity) / 5.0))  # log10(100k) = 5
    
    def _score_volume(self, volume_24h: float, trend: str) -> float:
        """
        Volume score: activity + trend confirmation.
        """
        # Base volume score
        if volume_24h <= 0:
            return 0.0
        if volume_24h >= 100000:
            base = 1.0
        elif volume_24h >= 10000:
            base = 0.7
        elif volume_24h >= 1000:
            base = 0.4
        else:
            base = 0.1
        
        # Trend adjustment
        trend_adj = {
            'increasing': +0.10,
            'decreasing': -0.10,
            'spiking': +0.15,
            'neutral': 0.0,
        }.get(trend.lower(), 0.0)
        
        return max(0.0, min(1.0, base + trend_adj))
    
    def _score_spread(self, bid: float, ask: float) -> float:
        """
        Spread score: tighter = better.
        0.5% → 1.0, 1% → 0.8, 2% → 0.4, 5%+ → 0
        """
        if bid <= 0 or ask <= 0:
            return 0.0
        spread_pct = (ask - bid) / ((bid + ask) / 2)
        
        if spread_pct <= 0.005:   # 0.5%
            return 1.0
        elif spread_pct <= 0.01:  # 1%
            return 0.8
        elif spread_pct <= 0.02:  # 2%
            return 0.6
        elif spread_pct <= 0.05:  # 5%
            return 0.3
        else:
            return 0.0
    
    def _score_momentum(self, price_change: float, trend: str, mid_price: float) -> float:
        """
        Momentum score: direction + strength + confirmation.
        """
        base = 0.5  # Neutral start
        
        # Price momentum
        if abs(price_change) > 0.20:
            base += 0.15 if price_change > 0 else -0.15
        elif abs(price_change) > 0.10:
            base += 0.10 if price_change > 0 else -0.10
        elif abs(price_change) > 0.05:
            base += 0.05 if price_change > 0 else -0.05
        
        # Trend confirmation
        if trend == 'increasing':
            base += 0.10
        elif trend == 'decreasing':
            base -= 0.10
        elif trend == 'spiking':
            base += 0.15  # Spike = strong momentum
        
        # Volume-momentum alignment (higher score if momentum aligns with volume)
        if price_change > 0 and trend == 'increasing':
            base += 0.05  # Bullish confirmation
        elif price_change < 0 and trend == 'decreasing':
            base += 0.05  # Bearish confirmation (good for SELL)
        
        return max(0.0, min(1.0, base))
    
    def _score_price_position(self, mid_price: float) -> float:
        """
        Price position score: optimal zone is 0.20-0.80.
        Avoid extremes (near 0 or 1 = binary outcome, no edge).
        """
        if mid_price <= 0.05 or mid_price >= 0.95:
            return 0.0  # Too extreme
        elif mid_price <= 0.10 or mid_price >= 0.90:
            return 0.3
        elif mid_price <= 0.20 or mid_price >= 0.80:
            return 0.6
        elif mid_price <= 0.30 or mid_price >= 0.70:
            return 0.9
        else:
            return 1.0  # Sweet spot 0.30-0.70
    
    def _score_time_decay(self, days_to_resolution: int, market_age_days: int) -> float:
        """
        Time decay: closer to resolution = more certainty.
        But too close (<1 day) = risk of unexpected events.
        """
        if days_to_resolution < 0:
            return 0.0  # Already resolved
        elif days_to_resolution < 1:
            return 0.3  # Very close — risky
        elif days_to_resolution < 3:
            return 0.9  # Sweet spot
        elif days_to_resolution < 7:
            return 0.8
        elif days_to_resolution < 14:
            return 0.6
        elif days_to_resolution < 30:
            return 0.4
        else:
            return 0.2  # Too far — too much uncertainty
    
    def _score_category(self, category: str) -> float:
        """
        Category score: based on predictability of category.
        Sports/Science > Politics > Crypto/Geopolitics
        """
        cat = category.lower().strip()
        profile = CATEGORY_PROFILES.get(cat, CATEGORY_PROFILES['default'])
        return max(0.0, min(1.0, profile['base_conf'] + profile['risk_adj']))
    
    def _score_market_age(self, age_days: int) -> float:
        """
        Market age: too new = unreliable, mature = price discovery done.
        """
        if age_days < 1:
            return 0.3   # Brand new — risky
        elif age_days < 3:
            return 0.6   # Settling
        elif age_days < 7:
            return 0.8   # Good
        elif age_days <= 60:
            return 1.0   # Sweet spot
        else:
            return 0.7   # Too old — may have stale price
    
    # ═══════════════════════════════════════════
    # SMART FILTERS
    # ═══════════════════════════════════════════
    
    def _smart_filter(self, score: MarketScore) -> Optional[MarketScore]:
        """
        Hard filters that override scoring.
        If any trigger → return HOLD with reason.
        """
        # Filter 1: Liquidity too low
        if score.liquidity_score < 0.25:
            score.total_score = 0.0
            score.action = 'HOLD'
            score.reason = f"REJECTED: Liquidity too low (score: {score.liquidity_score:.2f}). Need min $10k."
            return score
        
        # Filter 2: Spread too wide
        if score.spread_score < 0.20:
            score.total_score = 0.0
            score.action = 'HOLD'
            score.reason = "REJECTED: Spread too wide — execution cost too high."
            return score
        
        # Filter 3: Too close to resolution (<1h)
        if score.time_decay_score < 0.25:
            score.total_score = 0.0
            score.action = 'HOLD'
            score.reason = "REJECTED: Too close to resolution — unpredictable."
            return score
        
        # Filter 4: Volume dead
        if score.volume_score < 0.10:
            score.total_score = 0.0
            score.action = 'HOLD'
            score.reason = "REJECTED: No volume — dead market."
            return score
        
        return None
    
    # ═══════════════════════════════════════════
    # KELLY CRITERION POSITION SIZING
    # ═══════════════════════════════════════════
    
    def _kelly_criterion(self, confidence: float, price: float) -> float:
        """
        Kelly Criterion: f* = (bp - q) / b
        where:
            p = confidence (probability of winning)
            q = 1 - p (probability of losing)
            b = payout ratio (for binary market: (1-price)/price or price/(1-price))
        
        Returns: optimal fraction of capital to bet (capped at 25%).
        """
        if confidence <= 0.5:
            return 0.0  # No edge
        
        p = confidence
        q = 1 - p
        
        # Determine payout based on which side we're betting
        if price >= 0.5:
            # Betting YES — if price is 0.70, payout is 0.30/0.70 = 0.43
            b = (1 - price) / price if price > 0 else 0
        else:
            # Betting NO — if price is 0.30, payout is 0.70/0.30 = 2.33
            b = price / (1 - price) if price < 1 else 0
        
        if b <= 0:
            return 0.0
        
        kelly = (b * p - q) / b
        
        # Half-Kelly for safety (we're conservative)
        half_kelly = kelly / 2
        
        # Cap at 25% of capital
        return max(0.0, min(0.25, half_kelly))
    
    # ═══════════════════════════════════════════
    # PHASE THRESHOLDS
    # ═══════════════════════════════════════════
    
    def _get_phase_threshold(self) -> float:
        """Get minimum score threshold for BUY based on phase"""
        thresholds = {
            1: 0.75,  # Very strict
            2: 0.68,  # Strict
            3: 0.62,  # Moderate
            4: 0.55,  # Aggressive
        }
        return thresholds.get(self.phase, 0.75)
    
    # ═══════════════════════════════════════════
    # MEMORY ADJUSTMENT
    # ═══════════════════════════════════════════
    
    def _memory_adjustment(self, market_id: str, memory: Dict) -> float:
        """
        Adjust score based on historical performance with this market.
        """
        if not isinstance(memory, dict):
            return 0.0
        
        market_info = memory.get('markets', {}).get(market_id, {})
        if not market_info:
            return 0.0
        
        total_signals = market_info.get('total_signals', 0)
        successful = market_info.get('successful_signals', 0)
        
        if total_signals < 3:
            return 0.0  # Not enough data
        
        historical_win_rate = successful / total_signals
        
        # If historically profitable → boost
        if historical_win_rate > 0.65:
            return +0.05 * min((historical_win_rate - 0.65) / 0.35, 1.0)
        elif historical_win_rate < 0.40:
            return -0.05 * min((0.40 - historical_win_rate) / 0.40, 1.0)
        
        return 0.0
    
    # ═══════════════════════════════════════════
    # REASON GENERATION
    # ═══════════════════════════════════════════
    
    def _generate_detailed_reason(self, score: MarketScore, data: Dict) -> str:
        """Generate detailed breakdown of score components"""
        
        # Identify strongest factors
        factors = {
            'Liquidity': score.liquidity_score,
            'Volume': score.volume_score,
            'Spread': score.spread_score,
            'Momentum': score.momentum_score,
            'Price Position': score.price_position_score,
            'Time Decay': score.time_decay_score,
            'Category': score.category_score,
            'Market Age': score.market_age_score,
        }
        
        # Sort by score
        sorted_factors = sorted(factors.items(), key=lambda x: x[1], reverse=True)
        top_factors = [f"{k}({v:.2f})" for k, v in sorted_factors[:3]]
        weak_factors = [f"{k}({v:.2f})" for k, v in sorted_factors[-2:] if v < 0.5]
        
        # Build reason
        parts = []
        
        # Overall assessment
        if score.total_score >= 0.75:
            parts.append("STRONG BUY")
        elif score.total_score >= 0.60:
            parts.append("BUY")
        elif score.total_score >= 0.45:
            parts.append("MODERATE")
        elif score.total_score >= 0.30:
            parts.append("WEAK")
        else:
            parts.append("AVOID")
        
        parts.append(f"Score: {score.total_score:.2f}")
        
        # Category + edge
        profile = CATEGORY_PROFILES.get(score.category, CATEGORY_PROFILES['default'])
        parts.append(f"Edge: {profile['edge_type']}")
        
        # Top strengths
        parts.append(f"Strengths: {', '.join(top_factors)}")
        
        # Weaknesses if any
        if weak_factors:
            parts.append(f"Weak: {', '.join(weak_factors)}")
        
        # Kelly size
        if score.kelly_fraction > 0:
            parts.append(f"Kelly: {score.kelly_fraction:.1%} of capital")
        
        # Time info
        days = data.get('days_to_resolution', '?')
        parts.append(f"Resolution: {days}d")
        
        return " | ".join(parts)


# ═══════════════════════════════════════════
# RISK MANAGER
# ═══════════════════════════════════════════

@dataclass
class TradingSession:
    """Track current session state"""
    daily_trades: int = 0
    daily_pnl: float = 0.0
    open_positions: int = 0
    max_daily_loss_hit: bool = False
    total_exposure: float = 0.0


class RiskManager:
    """
    Multi-layer risk management with circuit breakers.
    """
    
    # Phase limits
    PHASE_LIMITS = {
        1: {'max_position': 0.05, 'max_daily_loss': 0.10, 'max_trades': 3, 'max_exposure': 0.15},
        2: {'max_position': 0.10, 'max_daily_loss': 0.15, 'max_trades': 5, 'max_exposure': 0.30},
        3: {'max_position': 0.15, 'max_daily_loss': 0.20, 'max_trades': 8, 'max_exposure': 0.50},
        4: {'max_position': 0.25, 'max_daily_loss': 0.25, 'max_trades': 12, 'max_exposure': 0.75},
    }
    
    def __init__(self, capital: float, phase: int = 1):
        self.capital = capital
        self.phase = phase
        self.session = TradingSession()
    
    def can_trade(self) -> Tuple[bool, str]:
        """Check if trading is allowed this session"""
        limits = self.PHASE_LIMITS.get(self.phase, self.PHASE_LIMITS[1])
        
        # Circuit breaker
        if self.session.max_daily_loss_hit:
            return False, "🛑 CIRCUIT BREAKER: Daily loss limit hit. Trading halted."
        
        # Daily loss check
        loss_pct = abs(self.session.daily_pnl) / self.capital if self.capital > 0 else 0
        if loss_pct >= limits['max_daily_loss']:
            self.session.max_daily_loss_hit = True
            return False, f"🛑 Daily loss {loss_pct:.1%} >= {limits['max_daily_loss']:.0%}"
        
        # Max trades
        if self.session.daily_trades >= limits['max_trades']:
            return False, f"Max daily trades reached: {self.session.daily_trades}/{limits['max_trades']}"
        
        # Max exposure
        exposure_pct = self.session.total_exposure / self.capital if self.capital > 0 else 0
        if exposure_pct >= limits['max_exposure']:
            return False, f"Max exposure reached: {exposure_pct:.1%}"
        
        return True, f"OK — Trades: {self.session.daily_trades}/{limits['max_trades']} | PnL: ${self.session.daily_pnl:+.2f}"
    
    def calculate_size(self, confidence: float, price: float, market_score: float) -> float:
        """
        Calculate position size using Kelly Criterion + phase limits.
        Returns: size in USD
        """
        limits = self.PHASE_LIMITS.get(self.phase, self.PHASE_LIMITS[1])
        
        # Kelly fraction
        kelly = LunaStrategy._kelly_criterion(LunaStrategy(), confidence, price)
        
        # Risk-adjusted Kelly (use score as multiplier)
        adjusted_kelly = kelly * (market_score / 0.75)  # Normalize to good score
        
        # Base size
        base_size = self.capital * min(adjusted_kelly, limits['max_position'])
        
        # Confidence multiplier
        conf_mult = 0.5 + (confidence * 0.5)  # 0.5 to 1.0
        
        final_size = base_size * conf_mult
        
        # Hard cap
        max_trade = self.capital * limits['max_position']
        final_size = min(final_size, max_trade)
        
        # Min trade size ($1)
        final_size = max(1.0, final_size) if final_size > 1.0 else 0.0
        
        return round(final_size, 2)
    
    def record_trade(self, pnl: float, size: float):
        """Record completed trade"""
        self.session.daily_trades += 1
        self.session.daily_pnl += pnl
        self.session.total_exposure += size
        
        # Check circuit breaker immediately
        loss_pct = abs(self.session.daily_pnl) / self.capital if self.capital > 0 else 0
        limits = self.PHASE_LIMITS.get(self.phase, self.PHASE_LIMITS[1])
        if loss_pct >= limits['max_daily_loss']:
            self.session.max_daily_loss_hit = True
            logger.warning(f"🛑 CIRCUIT BREAKER ACTIVATED: {loss_pct:.1%} daily loss")
    
    def reset_session(self):
        """Reset daily session (call at midnight UTC)"""
        self.session = TradingSession()
        logger.info("📅 Trading session reset")
    
    def update_exposure(self, delta: float):
        """Update total exposure (add when opening, reduce when closing)"""
        self.session.total_exposure = max(0, self.session.total_exposure + delta)
