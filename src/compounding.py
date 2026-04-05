# Phase 6: Compounding Protocol
# 1. Fractional Kelly (exact formula: f = c × ((p×b-q)/b))
# 2. Short Duration Priority (prefer < 168h)
# 3. Risk Offloading (exit before resolution when P_mkt aligns)
# 4. Capital Velocity (rotate if new EV > remaining potential)

import logging
import math
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 1. FRACTIONAL KELLY (EXACT FORMULA)
# ═══════════════════════════════════════════

class FractionalKelly:
    """
    Exact Kelly Criterion implementation matching blueprint:
    
    f = c × ((p × b - q) / b)
    
    Where:
      f = fraction of capital to allocate
      c = protective constant (0.25 or 0.5) — fractional Kelly
      p = probability of winning (P_bot)
      q = probability of losing (1 - p)
      b = payout ratio (odds)
    
    For YES bet on Polymarket:
      b = (1 - P_mkt) / P_mkt
    """
    
    def __init__(self, fractional_constant: float = 0.25, max_position_pct: float = 0.15):
        """
        Args:
            fractional_constant: 'c' in formula. 0.25 = quarter Kelly, 0.5 = half Kelly
            max_position_pct: Hard cap on any single position (% of capital)
        """
        self.c = fractional_constant
        self.max_position_pct = max_position_pct
    
    def calculate(self, p_bot: float, p_mkt: float) -> float:
        """
        Calculate position size fraction using exact formula.
        
        Returns fraction of capital (0.0 to max_position_pct).
        Returns 0.0 if no edge.
        """
        if p_bot <= p_mkt:
            return 0.0  # No edge
        
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
        
        # Apply fractional constant
        fractional = self.c * raw_kelly
        
        # Hard cap
        result = min(fractional, self.max_position_pct)
        
        return max(0.0, result)
    
    def explain(self, p_bot: float, p_mkt: float) -> str:
        """Human-readable breakdown of Kelly calculation"""
        if p_bot <= p_mkt:
            return f"No edge: P_bot({p_bot:.1%}) ≤ P_mkt({p_mkt:.1%})"
        
        p = p_bot
        q = 1.0 - p
        b = (1.0 - p_mkt) / p_mkt
        raw = (p * b - q) / b
        fractional = self.c * raw
        capped = min(fractional, self.max_position_pct)
        
        return (
            f"Kelly: c={self.c} × (({p:.3f}×{b:.3f}-{q:.3f})/{b:.3f}) "
            f"= raw {raw:.3%} → fractional {fractional:.3%} → capped {capped:.3%}"
        )


# ═══════════════════════════════════════════
# 2. SHORT DURATION PRIORITY
# ═══════════════════════════════════════════

class DurationScorer:
    """
    Score and prioritize markets by time-to-resolution.
    
    Blueprint: "Rotasi Instrumen Durasi Pendek"
    - Focus on contracts resolving within 168 hours (7 days)
    - Intraday (< 24h) gets highest priority
    - Faster resolution = faster compounding cycles
    """
    
    MAX_DURATION_HOURS = 168  # 7 days
    
    @classmethod
    def score(cls, hours_to_resolution: float) -> float:
        """
        Score from 0.0 to 1.0 based on duration.
        Shorter = higher score (faster compounding).
        """
        if hours_to_resolution <= 0:
            return 0.0  # Already resolved or invalid
        
        if hours_to_resolution <= 1:
            return 1.0  # Intraday — maximum compounding speed
        elif hours_to_resolution <= 6:
            return 0.95
        elif hours_to_resolution <= 24:
            return 0.85
        elif hours_to_resolution <= 72:
            return 0.75
        elif hours_to_resolution <= 168:
            return 0.60
        elif hours_to_resolution <= 336:  # 14 days
            return 0.30
        else:
            return 0.10  # Too slow for compounding
    
    @classmethod
    def is_short_duration(cls, hours_to_resolution: float) -> bool:
        """Check if market fits the short-duration rotation window"""
        return 0 < hours_to_resolution <= cls.MAX_DURATION_HOURS
    
    @classmethod
    def compounding_cycles_estimate(cls, hours_to_resolution: float) -> float:
        """Estimate how many cycles per month at this duration"""
        if hours_to_resolution <= 0:
            return 0
        hours_per_month = 720  # 30 days
        return hours_per_month / hours_to_resolution


# ═══════════════════════════════════════════
# 3. RISK OFFLOADING (EXIT BEFORE RESOLUTION)
# ═══════════════════════════════════════════

class RiskOffloader:
    """
    Protocol: "Likuidasi Pra-Resolusi"
    
    Sell before binary resolution (0 or 1) to lock in profit/cut loss.
    Active when P_mkt current aligns with P_bot entry estimate.
    
    Logic:
    - If P_mkt_current >= P_bot_entry - tolerance → lock profit
    - If position is profitable and resolution < 24h → exit
    - Avoid "binary event risk" in final hours
    """
    
    def __init__(self, tolerance: float = 0.03, min_profit_pct: float = 0.10):
        """
        Args:
            tolerance: How close P_mkt needs to be to P_bot to trigger
            min_profit_pct: Minimum unrealized gain % to consider offloading
        """
        self.tolerance = tolerance
        self.min_profit_pct = min_profit_pct
    
    def should_offload(self, 
                       entry_price: float,
                       current_price: float,
                       p_bot_entry: float,
                       p_mkt_current: float,
                       hours_to_resolution: float,
                       side: str = 'YES') -> Tuple[bool, str]:
        """
        Check if position should be offloaded before resolution.
        
        Returns: (should_exit, reason)
        """
        # Calculate unrealized PnL
        if side == 'YES':
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
        else:
            pnl_pct = (entry_price - current_price) / entry_price if entry_price > 0 else 0
        
        # RULE 1: Binary event risk — resolution < 24h and profitable
        if hours_to_resolution <= 24 and hours_to_resolution > 0:
            if pnl_pct >= self.min_profit_pct:
                return True, (
                    f"Binary risk: {hours_to_resolution:.1f}h to resolution, "
                    f"PnL {pnl_pct:+.1%} — locking profit"
                )
        
        # RULE 2: P_mkt has converged to P_bot — edge is realized
        if side == 'YES':
            # For YES bet: if market now prices it close to what we thought
            convergence = abs(p_mkt_current - p_bot_entry)
        else:
            convergence = abs((1 - p_mkt_current) - (1 - p_bot_entry))
        
        if convergence <= self.tolerance and pnl_pct >= self.min_profit_pct:
            return True, (
                f"Edge realized: P_mkt({p_mkt_current:.1%}) ≈ P_bot_entry({p_bot_entry:.1%}), "
                f"PnL {pnl_pct:+.1%} — taking profit"
            )
        
        # RULE 3: Resolution < 6h — always exit regardless
        if 0 < hours_to_resolution <= 6:
            if pnl_pct >= 0:
                return True, f"Imminent resolution ({hours_to_resolution:.1f}h), locking {pnl_pct:+.1%}"
            else:
                return True, f"Imminent resolution ({hours_to_resolution:.1f}h), cutting loss at {pnl_pct:+.1%}"
        
        return False, ""
    
    def calculate_exit_value(self, position_size: float, current_price: float, side: str) -> float:
        """Calculate what we'd get if we sold now"""
        if side == 'YES':
            return position_size * current_price
        else:
            # For NO shares: value = size * (1 - current_price)
            return position_size * (1 - current_price)


# ═══════════════════════════════════════════
# 4. CAPITAL VELOCITY OPTIMIZATION
# ═══════════════════════════════════════════

@dataclass
class VelocityAnalysis:
    """Result of capital velocity check"""
    should_rotate: bool
    reason: str
    remaining_potential: float  # $ expected from keeping current position
    new_opportunity_ev: float   # $ expected from new trade
    time_cost_hours: float      # Hours to resolution of current position
    velocity_ratio: float       # new_ev / remaining_potential


class CapitalVelocity:
    """
    Protocol: "Optimalisasi Biaya Peluang"
    
    Logic: Rotate position if
    (Remaining Potential / Time Remaining) < EV_New_Opportunity
    
    Meaning: If keeping the current position locks up capital that could
    earn MORE per hour elsewhere, rotate.
    """
    
    def __init__(self, min_velocity_ratio: float = 1.5):
        """
        Only rotate if new opportunity is at least 1.5x better
        (avoids excessive trading from marginal differences)
        """
        self.min_velocity_ratio = min_velocity_ratio
    
    def analyze(self,
                current_position_pnl: float,
                hours_to_resolution: float,
                entry_price: float,
                side: str,
                new_market_ev: float,
                new_market_duration_hours: float) -> VelocityAnalysis:
        """
        Analyze whether to keep or rotate capital.
        
        Args:
            current_position_pnl: Current unrealized PnL in $
            hours_to_resolution: Hours until current position resolves
            entry_price: Entry price of current position
            side: YES or NO
            new_market_ev: Expected value per $1 of new opportunity
            new_market_duration_hours: Duration of new opportunity
        """
        # Calculate remaining potential of current position
        if side == 'YES':
            max_payout = 1.0 - entry_price
        else:
            max_payout = entry_price
        
        # Value already gained
        current_value_ratio = current_position_pnl / max(1, abs(current_position_pnl) + 0.01)
        
        # Remaining value to capture
        remaining_potential = max(0, max_payout - abs(current_position_pnl))
        
        # Value per hour if we wait
        if hours_to_resolution > 0:
            current_velocity = remaining_potential / hours_to_resolution
        else:
            current_velocity = 0  # Already resolved
        
        # Value per hour if we rotate
        if new_market_duration_hours > 0:
            new_velocity = new_market_ev * 0.10 / new_market_duration_hours  # Assume $0.10 bet scale
        else:
            new_velocity = 0
        
        # Velocity ratio
        if remaining_potential > 0:
            velocity_ratio = new_market_ev / remaining_potential
        else:
            velocity_ratio = float('inf')  # No remaining potential, always rotate
        
        should_rotate = velocity_ratio >= self.min_velocity_ratio
        
        if should_rotate:
            reason = (
                f"Capital velocity: new opportunity (${new_market_ev:+.4f}/"
                f"{new_market_duration_hours:.0f}h) is {velocity_ratio:.1f}x better than "
                f"current (${remaining_potential:+.2f}/{hours_to_resolution:.0f}h)"
            )
        else:
            reason = (
                f"Hold: current position has better EV/time ratio "
                f"(ratio: {velocity_ratio:.2f}x < {self.min_velocity_ratio}x threshold)"
            )
        
        return VelocityAnalysis(
            should_rotate=should_rotate,
            reason=reason,
            remaining_potential=remaining_potential,
            new_opportunity_ev=new_market_ev,
            time_cost_hours=hours_to_resolution,
            velocity_ratio=velocity_ratio,
        )


# ═══════════════════════════════════════════
# COMPOUNDING ENGINE — orchestrates all 4
# ═══════════════════════════════════════════

class CompoundingEngine:
    """
    Master engine for Phase 6: Compounding Protocol.
    
    Coordinates:
    1. Fractional Kelly sizing
    2. Duration-based market scoring
    3. Risk offloading decisions
    4. Capital velocity optimization
    """
    
    def __init__(self, 
                 fractional_constant: float = 0.25,
                 max_position_pct: float = 0.15,
                 min_profit_offload: float = 0.10):
        self.kelly = FractionalKelly(
            fractional_constant=fractional_constant,
            max_position_pct=max_position_pct
        )
        self.offloader = RiskOffloader(min_profit_pct=min_profit_offload)
        self.velocity = CapitalVelocity()
    
    def size_position(self, p_bot: float, p_mkt: float) -> float:
        """Calculate position fraction using exact Fractional Kelly"""
        return self.kelly.calculate(p_bot, p_mkt)
    
    def score_duration(self, hours_to_resolution: float) -> float:
        """Score market by compounding efficiency"""
        return DurationScorer.score(hours_to_resolution)
    
    def check_offload(self, **kwargs) -> Tuple[bool, str]:
        """Check if position should be offloaded before resolution"""
        return self.offloader.should_offload(**kwargs)
    
    def check_velocity(self, **kwargs) -> VelocityAnalysis:
        """Check if capital should be rotated to new opportunity"""
        return self.velocity.analyze(**kwargs)
    
    def explain_kelly(self, p_bot: float, p_mkt: float) -> str:
        """Get human-readable Kelly breakdown"""
        return self.kelly.explain(p_bot, p_mkt)
