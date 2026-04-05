# Luna's EV-Based Trading Strategy Module
# Phase 5.1: Expected Value decision system — ONLY trade when P_bot > P_mkt AND EV > 0
# CRITICAL RULE: P_bot > 0.50 alone is NOT a trigger — only asymmetric divergence matters

import logging
import math
from datetime import datetime
from typing import Tuple, Dict, Any, NamedTuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# EV RESULT — structured return
# ═══════════════════════════════════════════
class EVResult(NamedTuple):
    action: str            # BUY | HOLD
    ev: float              # Expected value
    p_bot: float           # Our estimated probability
    p_mkt: float           # Market implied probability
    edge: float            # P_bot - P_mkt
    reason: str            # Human-readable explanation


# ═══════════════════════════════════════════
# MARKET CATEGORY PROFILES
# ═══════════════════════════════════════════
CATEGORY_PROFILES = {
    'crypto':       {'vol': 'high',   'base_conf': 0.55, 'risk_adj': -0.03, 'edge_type': 'momentum'},
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
    """Detailed scoring breakdown"""
    liquidity_score: float = 0.0
    volume_score: float = 0.0
    spread_score: float = 0.0
    momentum_score: float = 0.0
    price_position_score: float = 0.0
    time_decay_score: float = 0.0
    category_score: float = 0.0
    market_age_score: float = 0.0


class LunaStrategy:
    """
    Luna's EV-Based Trading Strategy — Phase 5.1
    
    GOLDEN RULE:
    ─────────────────────────────────────────────
    EV = (P_bot × W_net) - ((1 - P_bot) × C_total)
    
    IF EV > 0.00 → EXECUTE_ORDER
    IF EV ≤ 0.00 → ABORT_AND_SCAN_NEXT
    ─────────────────────────────────────────────
    
    P_bot > 0.50 ALONE IS NOT A TRIGGER!
    Only asymmetric divergence (P_bot > P_mkt) that yields EV > 0 matters.
    """
    
    # Scoring weights (same as Phase 2 — proven good)
    WEIGHTS = {
        'liquidity':      0.15,
        'volume':         0.15,
        'spread':         0.10,
        'momentum':       0.20,
        'price_position': 0.10,
        'time_decay':     0.10,
        'category':       0.10,
        'market_age':     0.10,
    }
    
    def __init__(self, phase: int = 1):
        self.phase = phase
        self._trade_log = []
    
    # ═══════════════════════════════════════════
    # MAIN ENTRY — EV ANALYSIS
    # ═══════════════════════════════════════════
    
    def analyze_market(self, market_data: Dict[str, Any], memory: Dict = None) -> EVResult:
        """
        Full EV analysis of a market.
        
        Returns EVResult with action, ev, p_bot, p_mkt, edge, reason.
        """
        # 1. Calculate 8-factor score → this becomes P_bot
        p_bot = self._calculate_multi_factor_score(market_data, memory)
        
        # 2. Get market-implied probability
        best_bid = market_data.get('best_bid', 0)
        best_ask = market_data.get('best_ask', 1)
        p_mkt = (best_bid + best_ask) / 2
        
        # 3. Calculate execution cost
        spread = best_ask - best_bid
        c_total = p_mkt + (spread * 0.5)  # Effective cost = mid + half-spread
        
        # 4. Net win projection
        w_net = 1.0 - c_total
        
        # 5. EXPECTED VALUE CALCULATION (THE CORE)
        ev = (p_bot * w_net) - ((1 - p_bot) * c_total)
        edge = p_bot - p_mkt
        
        # 6. EV GATE — absolute filter
        if not self._ev_gate(p_bot, p_mkt, ev):
            return self._build_reject_result(p_bot, p_mkt, ev, edge, market_data)
        
        # 7. Phase-based min EV threshold
        min_ev = self._get_min_ev_threshold()
        if ev < min_ev:
            return EVResult(
                action='HOLD',
                ev=ev,
                p_bot=p_bot,
                p_mkt=p_mkt,
                edge=edge,
                reason=f"+EV ${ev:+.4f} but below Phase {self.phase} minimum (${min_ev:.4f})"
            )
        
        # 8. Build acceptance result
        reason = self._build_accept_reason(p_bot, p_mkt, ev, edge, market_data, c_total, w_net)
        
        return EVResult(
            action='BUY',
            ev=ev,
            p_bot=p_bot,
            p_mkt=p_mkt,
            edge=edge,
            reason=reason,
        )
    
    def _ev_gate(self, p_bot: float, p_mkt: float, ev: float) -> bool:
        """
        CRITICAL EV FILTER — non-negotiable.
        
        Rule 1: P_bot must be > P_mkt (we must have an edge)
        Rule 2: EV must be positive
        Rule 3: P_bot > 0.50 ALONE is irrelevant
        """
        if p_bot <= p_mkt:
            return False  # No edge — market prices it higher than we estimate
        if ev <= 0:
            return False  # Even with edge, cost eats the value
        return True
    
    # ═══════════════════════════════════════════
    # 8-FACTOR SCORING → P_bot
    # ═══════════════════════════════════════════
    
    def _calculate_multi_factor_score(self, data: Dict, memory: Dict = None) -> float:
        """
        Calculate P_bot using weighted 8-factor model.
        Returns probability 0.0 - 1.0
        """
        score = MarketScore()
        
        # 1. Liquidity (15%)
        score.liquidity_score = self._score_liquidity(data.get('liquidity', 0))
        
        # 2. Volume (15%)
        score.volume_score = self._score_volume(
            data.get('volume_24h', 0),
            data.get('volume_trend', 'neutral')
        )
        
        # 3. Spread (10%)
        score.spread_score = self._score_spread(
            data.get('best_bid', 0), 
            data.get('best_ask', 1)
        )
        
        # 4. Momentum (20%)
        mid_price = (data.get('best_bid', 0) + data.get('best_ask', 1)) / 2
        score.momentum_score = self._score_momentum(
            data.get('price_change_24h', 0),
            data.get('volume_trend', 'neutral'),
            mid_price
        )
        
        # 5. Price Position (10%)
        score.price_position_score = self._score_price_position(mid_price)
        
        # 6. Time Decay (10%)
        score.time_decay_score = self._score_time_decay(
            data.get('days_to_resolution', 30),
            data.get('market_age_days', 0)
        )
        
        # 7. Category (10%)
        score.category_score = self._score_category(data.get('category', 'unknown'))
        
        # 8. Market Age (10%)
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
        
        # Memory adjustment
        if memory:
            memory_adj = self._memory_adjustment(data.get('id', ''), memory)
            weighted += memory_adj
        
        return max(0.0, min(1.0, weighted))
    
    # ═══════════════════════════════════════════
    # INDIVIDUAL SCORERS
    # ═══════════════════════════════════════════
    
    def _score_liquidity(self, liquidity: float) -> float:
        if liquidity <= 0: return 0.0
        if liquidity >= 100000: return 1.0
        return max(0.0, min(1.0, math.log10(liquidity) / 5.0))
    
    def _score_volume(self, volume_24h: float, trend: str) -> float:
        if volume_24h <= 0: return 0.0
        if volume_24h >= 100000: base = 1.0
        elif volume_24h >= 10000: base = 0.7
        elif volume_24h >= 1000: base = 0.4
        else: base = 0.1
        
        trend_adj = {'increasing': 0.10, 'decreasing': -0.10, 'spiking': 0.15, 'neutral': 0.0}
        return max(0.0, min(1.0, base + trend_adj.get(trend.lower(), 0.0)))
    
    def _score_spread(self, bid: float, ask: float) -> float:
        if bid <= 0 or ask <= 0: return 0.0
        spread_pct = (ask - bid) / ((bid + ask) / 2)
        if spread_pct <= 0.005: return 1.0
        elif spread_pct <= 0.01: return 0.8
        elif spread_pct <= 0.02: return 0.6
        elif spread_pct <= 0.05: return 0.3
        return 0.0
    
    def _score_momentum(self, price_change: float, trend: str, mid_price: float) -> float:
        base = 0.5
        
        if abs(price_change) > 0.20:
            base += 0.15 if price_change > 0 else -0.15
        elif abs(price_change) > 0.10:
            base += 0.10 if price_change > 0 else -0.10
        elif abs(price_change) > 0.05:
            base += 0.05 if price_change > 0 else -0.05
        
        trend_adj = {'increasing': 0.10, 'decreasing': -0.10, 'spiking': 0.15, 'neutral': 0.0}
        base += trend_adj.get(trend.lower(), 0.0)
        
        if price_change > 0 and trend == 'increasing':
            base += 0.05
        elif price_change < 0 and trend == 'decreasing':
            base += 0.05
        
        return max(0.0, min(1.0, base))
    
    def _score_price_position(self, mid_price: float) -> float:
        if mid_price <= 0.05 or mid_price >= 0.95: return 0.0
        elif mid_price <= 0.10 or mid_price >= 0.90: return 0.3
        elif mid_price <= 0.20 or mid_price >= 0.80: return 0.6
        elif mid_price <= 0.30 or mid_price >= 0.70: return 0.9
        return 1.0
    
    def _score_time_decay(self, days_to_resolution: int, market_age_days: int) -> float:
        if days_to_resolution < 0: return 0.0
        elif days_to_resolution < 1: return 0.3
        elif days_to_resolution < 3: return 0.9
        elif days_to_resolution < 7: return 0.8
        elif days_to_resolution < 14: return 0.6
        elif days_to_resolution < 30: return 0.4
        return 0.2
    
    def _score_category(self, category: str) -> float:
        cat = category.lower().strip()
        profile = CATEGORY_PROFILES.get(cat, CATEGORY_PROFILES['default'])
        return max(0.0, min(1.0, profile['base_conf'] + profile['risk_adj']))
    
    def _score_market_age(self, age_days: int) -> float:
        if age_days < 1: return 0.3
        elif age_days < 3: return 0.6
        elif age_days < 7: return 0.8
        elif age_days <= 60: return 1.0
        return 0.7
    
    def _memory_adjustment(self, market_id: str, memory: Dict) -> float:
        if not isinstance(memory, dict): return 0.0
        market_info = memory.get('markets', {}).get(market_id, {})
        if not market_info: return 0.0
        
        total = market_info.get('total_signals', 0)
        successful = market_info.get('successful_signals', 0)
        if total < 3: return 0.0
        
        win_rate = successful / total
        if win_rate > 0.65:
            return +0.05 * min((win_rate - 0.65) / 0.35, 1.0)
        elif win_rate < 0.40:
            return -0.05 * min((0.40 - win_rate) / 0.40, 1.0)
        return 0.0
    
    # ═══════════════════════════════════════════
    # KELLY CRITERION — position sizing from edge
    # ═══════════════════════════════════════════
    
    @staticmethod
    def kelly_fraction(p_bot: float, p_mkt: float, fractional_constant: float = 0.25) -> float:
        """
        Phase 6: EXACT Fractional Kelly Criterion
        
        f = c × ((p × b - q) / b)
        
        Where:
          c = fractional constant (0.25 = quarter Kelly for safety)
          p = P_bot (our estimated probability)
          q = 1 - p (probability of losing)
          b = (1 - P_mkt) / P_mkt (payout ratio for YES bet)
        
        Half-Kelly fallback, capped at 15%.
        Returns 0.0 if no edge.
        """
        if p_bot <= p_mkt:
            return 0.0  # No edge — don't bet
        
        if p_mkt <= 0.01 or p_mkt >= 0.99:
            return 0.0  # Too extreme, odds unreliable
        
        p = p_bot
        q = 1.0 - p
        b = (1.0 - p_mkt) / p_mkt  # Payout ratio for YES bet
        
        if b <= 0:
            return 0.0
        
        # EXACT FORMULA: f = c × ((p × b - q) / b)
        raw_kelly = (p * b - q) / b
        
        if raw_kelly <= 0:
            return 0.0
        
        # Apply fractional constant (default 0.25 = quarter Kelly)
        fractional = fractional_constant * raw_kelly
        
        return max(0.0, min(0.15, fractional))
    
    # ═══════════════════════════════════════════
    # PHASE THRESHOLDS
    # ═══════════════════════════════════════════
    
    def _get_min_ev_threshold(self) -> float:
        """Minimum EV required, by phase"""
        return {
            1: 0.05,  # Need 5¢ edge per $1 bet
            2: 0.03,
            3: 0.02,
            4: 0.01,
        }.get(self.phase, 0.05)
    
    # ═══════════════════════════════════════════
    # REASON BUILDERS
    # ═══════════════════════════════════════════
    
    def _build_reject_result(self, p_bot, p_mkt, ev, edge, data):
        """Build rejection result with clear reason"""
        if p_bot <= p_mkt:
            reason = (f"NO EDGE: Our {p_bot:.1%} ≤ Market {p_mkt:.1%} "
                     f"(divergence: {edge:+.1%}). No asymmetric value.")
        else:
            reason = f"-EV: Edge exists but spread cost kills it (EV: ${ev:+.4f})"
        
        return EVResult(
            action='HOLD',
            ev=ev,
            p_bot=p_bot,
            p_mkt=p_mkt,
            edge=edge,
            reason=reason,
        )
    
    def _build_accept_reason(self, p_bot, p_mkt, ev, edge, data, c_total, w_net):
        """Build detailed acceptance reason"""
        side = 'YES' if p_bot > p_mkt else 'NO'
        cat = data.get('category', 'unknown')
        vol_24h = data.get('volume_24h', 0)
        liq = data.get('liquidity', 0)
        
        kelly = self.kelly_fraction(p_bot, p_mkt)
        
        return (
            f"+EV ${ev:+.4f} | {side} | "
            f"Our {p_bot:.1%} vs Market {p_mkt:.1%} (edge: {edge:+.1%}) | "
            f"Cost: ${c_total:.4f} | WinNet: ${w_net:.4f} | "
            f"Kelly: {kelly:.1%} | "
            f"Vol: ${vol_24h:,.0f} | Liq: ${liq:,.0f} | {cat}"
        )


# ═══════════════════════════════════════════
# RISK MANAGER — EV-aware position sizing
# ═══════════════════════════════════════════

@dataclass
class TradingSession:
    daily_trades: int = 0
    daily_pnl: float = 0.0
    open_positions: int = 0
    max_daily_loss_hit: bool = False
    total_exposure: float = 0.0


class RiskManager:
    """Multi-layer risk management with EV-aware sizing"""
    
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
        limits = self.PHASE_LIMITS.get(self.phase, self.PHASE_LIMITS[1])
        
        if self.session.max_daily_loss_hit:
            return False, "🛑 CIRCUIT BREAKER: Daily loss limit hit"
        
        loss_pct = abs(self.session.daily_pnl) / self.capital if self.capital > 0 else 0
        if loss_pct >= limits['max_daily_loss']:
            self.session.max_daily_loss_hit = True
            return False, f"🛑 Daily loss {loss_pct:.1%} >= {limits['max_daily_loss']:.0%}"
        
        if self.session.daily_trades >= limits['max_trades']:
            return False, f"Max trades: {self.session.daily_trades}/{limits['max_trades']}"
        
        exposure_pct = self.session.total_exposure / self.capital if self.capital > 0 else 0
        if exposure_pct >= limits['max_exposure']:
            return False, f"Max exposure: {exposure_pct:.1%}"
        
        return True, f"OK — {self.session.daily_trades}/{limits['max_trades']} trades | PnL: ${self.session.daily_pnl:+.2f}"
    
    def calculate_size(self, p_bot: float, p_mkt: float, capital_override: float = None) -> float:
        """
        Calculate position size using Kelly Criterion.
        
        ONLY called when EV > 0 (pre-validated by strategy).
        
        Args:
            p_bot: Our probability estimate
            p_mkt: Market implied probability
            capital_override: Optional — use specific capital instead of self.capital
        """
        limits = self.PHASE_LIMITS.get(self.phase, self.PHASE_LIMITS[1])
        
        # Kelly fraction based on edge
        kelly = LunaStrategy.kelly_fraction(p_bot, p_mkt)
        
        if kelly <= 0:
            return 0.0  # Should never happen — EV gate should catch this
        
        # Apply phase limit
        cap = capital_override or self.capital
        base_size = cap * min(kelly, limits['max_position'])
        
        # Edge-strengthened: more edge = bigger bet (but capped)
        edge = p_bot - p_mkt
        edge_multiplier = 0.5 + min(edge / 0.10, 0.5)  # 0.5x at 0 edge, 1.0x at 10%+ edge
        final_size = base_size * edge_multiplier
        
        # Hard cap
        max_trade = cap * limits['max_position']
        final_size = min(final_size, max_trade)
        
        # Min $1 trade
        if final_size < 1.0:
            return 0.0
        
        return round(final_size, 2)
    
    def record_trade(self, pnl: float, size: float):
        self.session.daily_trades += 1
        self.session.daily_pnl += pnl
        self.session.total_exposure += size
        
        loss_pct = abs(self.session.daily_pnl) / self.capital if self.capital > 0 else 0
        limits = self.PHASE_LIMITS.get(self.phase, self.PHASE_LIMITS[1])
        if loss_pct >= limits['max_daily_loss']:
            self.session.max_daily_loss_hit = True
            logger.warning(f"🛑 CIRCUIT BREAKER: {loss_pct:.1%} daily loss")
    
    def reset_session(self):
        self.session = TradingSession()
        logger.info("📅 Trading session reset")
    
    def update_exposure(self, delta: float):
        self.session.total_exposure = max(0, self.session.total_exposure + delta)
