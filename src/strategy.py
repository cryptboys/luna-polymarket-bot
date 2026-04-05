# Luna's Trading Strategy Module
# Conservative, High-Probability, Phase-Based

import logging
from datetime import datetime
from typing import Tuple, Dict, Any

logger = logging.getLogger(__name__)

# Market categories and their typical behavior
CATEGORIES = {
    'crypto': {'volatility': 'high', 'confidence_adj': -0.05},
    'politics': {'volatility': 'medium', 'confidence_adj': 0.0},
    'sports': {'volatility': 'medium', 'confidence_adj': 0.0},
    'entertainment': {'volatility': 'low', 'confidence_adj': +0.05},
    'science': {'volatility': 'low', 'confidence_adj': +0.05},
    'geopolitics': {'volatility': 'high', 'confidence_adj': -0.05},
    'business': {'volatility': 'medium', 'confidence_adj': 0.0},
    'tech': {'volatility': 'high', 'confidence_adj': -0.03},
}

class LunaStrategy:
    """
    Luna's Conservative Trading Strategy
    Focus: High-probability setups, strict risk management
    """
    
    # Market categories and their typical behavior
    CATEGORIES = {
        'crypto': {'volatility': 'high', 'confidence_adj': -0.05},
        'politics': {'volatility': 'medium', 'confidence_adj': 0.0},
        'sports': {'volatility': 'medium', 'confidence_adj': 0.0},
        'entertainment': {'volatility': 'low', 'confidence_adj': +0.05},
        'science': {'volatility': 'low', 'confidence_adj': +0.05},
        'geopolitics': {'volatility': 'high', 'confidence_adj': -0.05}
    }
    
    def __init__(self, phase: int = 1):
        self.phase = phase
        self.min_liquidity = 10000  # $10k minimum
        self.max_spread = 0.02  # 2% max spread
        
    def analyze_market(self, market_data: Dict[str, Any], memory: Dict = None) -> Tuple[str, float, str]:
        """
        Analyze a single market and return trading signal
        
        Returns:
            (action, confidence, reason)
            action: 'BUY' | 'SELL' | 'HOLD'
            confidence: 0.0 - 1.0
            reason: explanation string
        """
        
        # Basic filters
        if not self._pass_basic_filters(market_data):
            return 'HOLD', 0.0, 'Failed basic filters'
        
        # Calculate base confidence
        confidence = self._calculate_base_confidence(market_data)
        
        # Apply adjustments
        confidence = self._apply_market_adjustments(market_data, confidence)
        confidence = self._apply_temporal_adjustments(market_data, confidence)
        confidence = self._apply_memory_adjustments(market_data, confidence, memory)
        
        # Determine action
        action = self._determine_action(market_data, confidence)
        
        reason = self._generate_reason(market_data, confidence, action)
        
        return action, confidence, reason
    
    def _pass_basic_filters(self, market_data: Dict) -> bool:
        """Basic market quality filters"""
        
        # Liquidity check
        liquidity = market_data.get('liquidity', 0)
        if liquidity < self.min_liquidity:
            return False
        
        # Spread check
        best_bid = market_data.get('best_bid', 0)
        best_ask = market_data.get('best_ask', 1)
        spread = best_ask - best_bid
        if spread > self.max_spread:
            return False
        
        # Price extremity check (avoid 0.01 or 0.99)
        mid_price = (best_bid + best_ask) / 2
        if mid_price < 0.05 or mid_price > 0.95:
            return False
        
        # Volume check
        volume_24h = market_data.get('volume_24h', 0)
        if volume_24h < 1000:  # Min $1k daily volume
            return False
        
        return True
    
    def _calculate_base_confidence(self, market_data: Dict) -> float:
        """Calculate base confidence from market metrics"""
        
        confidence = 0.5  # Start neutral
        
        # Price momentum
        price_change_24h = market_data.get('price_change_24h', 0)
        if abs(price_change_24h) > 0.10:  # >10% move
            confidence += 0.10 if price_change_24h > 0 else -0.10
        
        # Volume trend
        volume_trend = market_data.get('volume_trend', 'neutral')
        if volume_trend == 'increasing':
            confidence += 0.05
        elif volume_trend == 'decreasing':
            confidence -= 0.05
        
        # Order book imbalance
        bid_ask_ratio = market_data.get('bid_ask_ratio', 1.0)
        if bid_ask_ratio > 1.5:
            confidence += 0.05  # More bids = bullish
        elif bid_ask_ratio < 0.67:
            confidence -= 0.05  # More asks = bearish
        
        # Clamp to valid range
        return max(0.0, min(1.0, confidence))
    
    def _apply_market_adjustments(self, market_data: Dict, confidence: float) -> float:
        """Apply category-specific adjustments"""
        
        category = market_data.get('category', 'unknown')
        cat_config = self.CATEGORIES.get(category, {})
        
        confidence += cat_config.get('confidence_adj', 0)
        
        # Time to resolution adjustment
        days_to_resolve = market_data.get('days_to_resolution', 30)
        if days_to_resolve < 1:
            confidence -= 0.10  # Too close to resolution, avoid
        elif days_to_resolve > 90:
            confidence -= 0.05  # Too far, less certainty
        
        return max(0.0, min(1.0, confidence))
    
    def _apply_temporal_adjustments(self, market_data: Dict, confidence: float) -> float:
        """Apply time-based adjustments"""
        
        # News recency
        last_news_hours = market_data.get('last_news_hours', 999)
        if last_news_hours < 1:
            confidence -= 0.05  # Very fresh news, wait for stabilization
        elif last_news_hours < 24:
            confidence += 0.03  # Recent news, still relevant
        
        # Market age
        market_age_days = market_data.get('market_age_days', 0)
        if market_age_days < 1:
            confidence -= 0.10  # Brand new market, avoid
        
        return max(0.0, min(1.0, confidence))
    
    def _apply_memory_adjustments(self, market_data: Dict, confidence: float, memory: Dict = None) -> float:
        """Apply historical performance adjustments"""
        
        if not memory:
            return confidence
        
        market_id = market_data.get('id')
        market_memory = memory.get('markets', {}).get(market_id, {})
        
        if market_memory:
            historical_win_rate = market_memory.get('win_rate', 0.5)
            total_signals = market_memory.get('total_signals', 0)
            
            if total_signals >= 5:
                # Adjust based on historical performance
                confidence += (historical_win_rate - 0.5) * 0.10
        
        return max(0.0, min(1.0, confidence))
    
    def _determine_action(self, market_data: Dict, confidence: float) -> str:
        """Determine buy/sell/hold based on confidence"""
        
        # Phase-based thresholds
        thresholds = {
            1: 0.80,  # Phase 1: Very conservative
            2: 0.75,  # Phase 2: Conservative
            3: 0.70,  # Phase 3: Moderate
            4: 0.65   # Phase 4: Aggressive
        }
        
        threshold = thresholds.get(self.phase, 0.80)
        
        if confidence >= threshold:
            return 'BUY'
        elif confidence <= (1 - threshold):
            return 'SELL'
        
        return 'HOLD'
    
    def _generate_reason(self, market_data: Dict, confidence: float, action: str) -> str:
        """Generate human-readable reason for the signal"""
        
        reasons = []
        
        if action == 'HOLD':
            reasons.append(f"Confidence {confidence:.1%} below threshold")
        else:
            reasons.append(f"Confidence {confidence:.1%} meets threshold")
        
        # Add specific factors
        liquidity = market_data.get('liquidity', 0)
        reasons.append(f"Liquidity: ${liquidity:,.0f}")
        
        category = market_data.get('category', 'unknown')
        reasons.append(f"Category: {category}")
        
        return " | ".join(reasons)

class RiskManager:
    """Risk management and position sizing"""
    
    def __init__(self, capital: float, phase: int = 1):
        self.capital = capital
        self.phase = phase
        
        # Phase-based limits
        self.limits = {
            1: {'max_position': 0.05, 'max_daily_loss': 0.10, 'max_trades': 3},
            2: {'max_position': 0.10, 'max_daily_loss': 0.15, 'max_trades': 5},
            3: {'max_position': 0.15, 'max_daily_loss': 0.20, 'max_trades': 7},
            4: {'max_position': 0.25, 'max_daily_loss': 0.25, 'max_trades': 10}
        }
    
    def calculate_position_size(self, confidence: float, price: float = 0.5) -> float:
        """Calculate position size with risk adjustments"""
        
        limit = self.limits.get(self.phase, self.limits[1])
        base_size = self.capital * limit['max_position']
        
        # Confidence adjustment
        conf_mult = min(confidence / 0.80, 1.5)
        
        # Price uncertainty adjustment
        uncertainty = 1 - abs(price - 0.5) * 2
        price_adj = 0.5 + (uncertainty * 0.5)
        
        size = base_size * conf_mult * price_adj
        
        # Hard cap at 25% of capital
        max_abs = self.capital * 0.25
        
        return round(min(size, max_abs), 2)
    
    def can_trade(self, daily_pnl: float, open_positions: int) -> Tuple[bool, str]:
        """Check if trading is allowed"""
        
        limit = self.limits.get(self.phase, self.limits[1])
        
        # Daily loss check
        daily_loss_pct = abs(daily_pnl) / self.capital if self.capital > 0 else 0
        if daily_loss_pct >= limit['max_daily_loss']:
            return False, f"Daily loss limit hit: {daily_loss_pct*100:.1f}%"
        
        # Max positions check
        if open_positions >= limit['max_trades']:
            return False, f"Max open positions: {open_positions}/{limit['max_trades']}"
        
        return True, "OK"
