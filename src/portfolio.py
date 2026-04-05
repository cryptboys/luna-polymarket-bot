# Position Lifecycle & Portfolio Manager
# Phase 3: Auto-expiry, rebalancing, PnL tracking, health monitoring

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class PositionState(Enum):
    OPEN = "open"
    IN_RANGE = "in_range"
    OUT_OF_RANGE = "out_of_range"
    CLOSING = "closing"
    CLOSED = "closed"
    EXPIRED = "expired"


@dataclass
class Position:
    """Track a single open position"""
    position_id: str
    market_id: str
    market_name: str
    side: str  # YES or NO
    entry_price: float
    entry_time: str
    size: float
    kelly_fraction: float
    market_score: float
    confidence: float
    phase: int
    state: PositionState = PositionState.OPEN
    pnl_realized: float = 0.0
    pnl_unrealized: float = 0.0
    current_price: float = 0.0
    tp_hit: bool = False
    sl_hit: bool = False
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    notes: str = ""
    
    @property
    def age_minutes(self) -> float:
        try:
            entry = datetime.fromisoformat(self.entry_time)
            return (datetime.now() - entry).total_seconds() / 60
        except:
            return 0
    
    @property
    def pnl_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        if self.exit_price:
            return ((self.exit_price - self.entry_price) / self.entry_price) * 100
        if self.current_price <= 0:
            return 0.0
        if self.side == 'YES':
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - self.current_price) / self.entry_price) * 100
    
    @property
    def potential_payout(self) -> float:
        """If market resolves in our favor"""
        if self.side == 'YES':
            return self.size * (1 - self.entry_price) / self.entry_price
        else:
            return self.size * self.entry_price / (1 - self.entry_price)


class PortfolioManager:
    """
    Manages all open positions with lifecycle tracking.
    
    Features:
    - Auto-check expiry (close before resolution)
    - PnL tracking (realized + unrealized)
    - Exposure management
    - Auto-rebalancing
    - Health monitoring
    """
    
    def __init__(self, capital: float, phase: int = 1, db_memory = None):
        self.capital = capital
        self.phase = phase
        self.db = db_memory
        self.positions: Dict[str, Position] = {}
        self.closed_positions: List[Position] = []
        
        # Lifecycle config
        self.close_before_resolution_hours = int(os.getenv('CLOSE_BEFORE_RES_HOURS', 24))
        self.max_holding_hours = int(os.getenv('MAX_HOLDING_HOURS', 168))  # 7 days
        self.tp_pct = float(os.getenv('TP_PCT', 50))  # Take profit at 50% gain
        self.sl_pct = float(os.getenv('SL_PCT', 30))  # Stop loss at 30% loss
        
        # Rebalancing
        self.rebalance_threshold = 0.10  # 10% deviation from target
        self.profit_reinvest_pct = float(os.getenv('PROFIT_REINVEST_PCT', 0.5))  # 50% of profits reinvested
        
        # Health
        self.last_health_check = 0
        self.health_check_interval = 60  # seconds
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5
    
    # ═══════════════════════════════════════════
    # POSITION LIFECYCLE
    # ═══════════════════════════════════════════
    
    def open_position(self, position_id: str, market_id: str, market_name: str,
                      side: str, entry_price: float, size: float,
                      kelly_fraction: float = 0, market_score: float = 0,
                      confidence: float = 0) -> Position:
        """Open a new position"""
        pos = Position(
            position_id=position_id,
            market_id=market_id,
            market_name=market_name,
            side=side,
            entry_price=entry_price,
            entry_time=datetime.now().isoformat(),
            size=size,
            kelly_fraction=kelly_fraction,
            market_score=market_score,
            confidence=confidence,
            phase=self.phase,
        )
        self.positions[position_id] = pos
        
        # Log to database
        if self.db:
            self.db.log_trade({
                'market_id': market_id,
                'market_name': market_name,
                'action': 'BUY',
                'side': side,
                'size': size,
                'price': entry_price,
                'confidence': confidence,
                'market_score': market_score,
                'kelly_fraction': kelly_fraction,
                'phase': self.phase,
            })
        
        logger.info(f"📈 New position: {side} ${size:.2f} @ ${entry_price:.3f} on {market_name[:40]}")
        return pos
    
    def close_position(self, position_id: str, exit_price: float, reason: str = "manual") -> Optional[Position]:
        """Close a position"""
        pos = self.positions.get(position_id)
        if not pos:
            logger.warning(f"Position {position_id} not found for closing")
            return None
        
        pos.exit_price = exit_price
        pos.exit_time = datetime.now().isoformat()
        pos.exit_reason = reason
        pos.current_price = exit_price
        pos.state = PositionState.CLOSED
        
        # Calculate PnL
        pnl_pct = pos.pnl_pct / 100  # Convert from percentage to decimal
        pos.pnl_realized = pos.size * pnl_pct
        pos.pnl_unrealized = 0
        
        # Update capital
        self.capital += pos.pnl_realized
        
        # Move to closed
        self.closed_positions.append(pos)
        del self.positions[position_id]
        
        # Log to database
        if self.db:
            self.db.close_trade(
                trade_id=-1,  # Would need trade_id from open_position
                exit_price=exit_price,
                pnl=pos.pnl_realized,
                lesson=f"Exit: {reason}, PnL: ${pos.pnl_realized:+.2f}"
            )
        
        logger.info(f"📉 Closed position: {pos.market_name[:40]} — PnL: ${pos.pnl_realized:+.2f} ({pnl_pct:+.1%}) | Reason: {reason}")
        return pos
    
    # ═══════════════════════════════════════════
    # LIFECYCLE CHECKS
    # ═══════════════════════════════════════════
    
    def check_lifecycle(self, market_prices: Dict[str, float], 
                        market_resolution: Dict[str, Dict]) -> List[Tuple[str, str, float]]:
        """
        Check all open positions for lifecycle events.
        
        Returns list of (position_id, reason, exit_price) for positions to close.
        """
        to_close = []
        
        for pid, pos in list(self.positions.items()):
            mid = pos.market_id
            current_price = market_prices.get(mid, pos.current_price)
            pos.current_price = current_price
            
            # 1. EXPIRY CHECK — close before resolution
            resolution_info = market_resolution.get(mid, {})
            resolution_date_str = resolution_info.get('end_date_iso', '')
            if resolution_date_str:
                try:
                    from datetime import timezone
                    res_date = datetime.fromisoformat(resolution_date_str.replace("Z", "+00:00"))
                    hours_until_resolution = (res_date - datetime.now(res_date.tzinfo)).total_seconds() / 3600
                    if 0 < hours_until_resolution < self.close_before_resolution_hours:
                        to_close.append((pid, f"Expiry approaching ({hours_until_resolution:.1f}h left)", current_price))
                        pos.state = PositionState.CLOSING
                        logger.info(f"⏰ Position {pos.market_name[:30]}: Resolution in {hours_until_resolution:.1f}h — preparing close")
                    elif hours_until_resolution <= 0:
                        to_close.append((pid, "Market resolved", self._get_resolution_outcome(mid, resolution_info)))
                        logger.info(f"🏁 Market resolved: {pos.market_name[:30]}")
                except:
                    pass
            
            # 2. HOLDING TIME CHECK — max position age
            if pos.age_minutes > self.max_holding_hours * 60:
                to_close.append((pid, f"Max holding time ({self.max_holding_hours}h) reached", current_price))
                logger.info(f"⏱️ Position {pos.market_name[:30]}: Max holding time reached")
            
            # 3. TAKE PROFIT CHECK
            if pos.pnl_pct >= self.tp_pct and not pos.tp_hit:
                pos.tp_hit = True
                to_close.append((pid, f"Take profit {self.tp_pct}% hit (PnL: {pos.pnl_pct:.1f}%)", current_price))
                logger.info(f"💰 TP hit: {pos.market_name[:30]} — {pos.pnl_pct:.1f}% gain")
            
            # 4. STOP LOSS CHECK
            if pos.pnl_pct <= -self.sl_pct and not pos.sl_hit:
                pos.sl_hit = True
                to_close.append((pid, f"Stop loss {self.sl_pct}% hit (PnL: {pos.pnl_pct:.1f}%)", current_price))
                logger.info(f"🛑 SL hit: {pos.market_name[:30]} — {pos.pnl_pct:.1f}% loss")
            
            # 5. STATE UPDATES
            if current_price > 0:
                spread = abs(current_price - pos.entry_price) / pos.entry_price
                if spread < 0.01:
                    pos.state = PositionState.IN_RANGE
                else:
                    pos.state = PositionState.OUT_OF_RANGE
        
        return to_close
    
    def _get_resolution_outcome(self, market_id: str, resolution_info: Dict) -> float:
        """Get resolution outcome price (0 or 1 for binary market)"""
        # Would need actual settlement data from Polymarket
        # For now, return exit at current price
        return 0.5
    
    # ═══════════════════════════════════════════
    # PORTFOLIO SUMMARY
    # ═══════════════════════════════════════════
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get current portfolio overview"""
        total_exposure = sum(p.size for p in self.positions.values())
        total_unrealized = sum(p.pnl_unrealized for p in self.positions.values())
        total_realized = sum(p.pnl_realized for p in self.closed_positions)
        
        # Position breakdown by category/state
        by_state = {}
        for p in self.positions.values():
            state = p.state.value
            by_state[state] = by_state.get(state, 0) + 1
        
        # Win rate
        closed_wins = sum(1 for p in self.closed_positions if p.pnl_realized > 0)
        closed_total = len(self.closed_positions)
        win_rate = closed_wins / closed_total if closed_total > 0 else 0
        
        # Average trade metrics
        avg_pnl = total_realized / closed_total if closed_total > 0 else 0
        avg_hold_time = (
            sum(p.age_minutes for p in self.closed_positions) / closed_total
            if closed_total > 0 else 0
        )
        
        # Exposure by side
        yes_exposure = sum(p.size for p in self.positions.values() if p.side == 'YES')
        no_exposure = sum(p.size for p in self.positions.values() if p.side == 'NO')
        
        return {
            'capital': self.capital,
            'total_exposure': total_exposure,
            'exposure_pct': (total_exposure / self.capital * 100) if self.capital > 0 else 0,
            'total_unrealized_pnl': total_unrealized,
            'total_realized_pnl': total_realized,
            'open_positions': len(self.positions),
            'closed_positions': closed_total,
            'win_rate': win_rate,
            'avg_pnl_per_trade': avg_pnl,
            'avg_hold_time_minutes': avg_hold_time,
            'positions_by_state': by_state,
            'yes_exposure': yes_exposure,
            'no_exposure': no_exposure,
            'phase': self.phase,
        }
    
    def get_open_positions_detail(self) -> List[Dict]:
        """Get detailed info on all open positions"""
        result = []
        for pid, pos in self.positions.items():
            result.append({
                'id': pos.position_id,
                'market': pos.market_name[:50],
                'market_id': pos.market_id,
                'side': pos.side,
                'entry': pos.entry_price,
                'current': pos.current_price,
                'size': pos.size,
                'pnl_pct': pos.pnl_pct,
                'pnl_usd': pos.pnl_unrealized,
                'tp_hit': pos.tp_hit,
                'sl_hit': pos.sl_hit,
                'age_hours': pos.age_minutes / 60,
                'kelly': pos.kelly_fraction,
                'state': pos.state.value,
            })
        return result
    
    # ═══════════════════════════════════════════
    # REBALANCING
    # ═══════════════════════════════════════════
    
    def check_rebalance(self) -> Optional[Dict[str, Any]]:
        """
        Check if portfolio needs rebalancing.
        
        Strategy:
        1. If one position > 50% of total exposure → reduce it
        2. If exposure > max for phase → close lowest-score position
        3. If profit > X% → reinvest 50% of profits
        
        Returns rebalance action if needed.
        """
        if not self.positions:
            return None
        
        total_exposure = sum(p.size for p in self.positions.values())
        
        # Check single position concentration
        largest = max(self.positions.values(), key=lambda p: p.size)
        if largest.size > total_exposure * 0.50:
            return {
                'action': 'reduce_largest',
                'position_id': largest.position_id,
                'reason': f"Position is {largest.size/total_exposure*100:.0f}% of exposure (max 50%)",
                'reduce_pct': 0.25,  # Reduce by 25%
            }
        
        # Check total exposure vs phase limits
        phase_limits = {
            1: 0.15,
            2: 0.30,
            3: 0.50,
            4: 0.75,
        }
        max_exposure = self.capital * phase_limits.get(self.phase, 0.15)
        
        if total_exposure > max_exposure:
            # Close lowest-score position
            lowest_score = min(self.positions.values(), key=lambda p: p.market_score)
            return {
                'action': 'close_lowest_score',
                'position_id': lowest_score.position_id,
                'reason': f"Total exposure ${total_exposure:.2f} exceeds max ${max_exposure:.2f} for Phase {self.phase}",
            }
        
        # Check if we should reinvest profits
        total_profit = sum(p.pnl_realized for p in self.closed_positions if p.pnl_realized > 0)
        if total_profit > self.capital * 0.05:  # 5% profit threshold
            reinvest = total_profit * self.profit_reinvest_pct
            return {
                'action': 'reinvest_profit',
                'amount': reinvest,
                'reason': f"Available profit ${total_profit:.2f} — reinvesting {self.profit_reinvest_pct*100:.0f}% (${reinvest:.2f})",
            }
        
        return None
    
    # ═══════════════════════════════════════════
    # HEALTH MONITORING
    # ═══════════════════════════════════════════
    
    def health_check(self) -> Dict[str, Any]:
        """
        Run system health check.
        Returns status + recommendations.
        """
        now = time.time()
        if now - self.last_health_check < self.health_check_interval:
            return {'status': 'ok', 'checked_at': self.last_health_check}
        
        self.last_health_check = now
        
        issues = []
        recommendations = []
        
        # 1. Check stale positions (no price update)
        for pid, pos in self.positions.items():
            if pos.age_minutes > self.max_holding_hours * 60:
                issues.append(f"Stale position: {pos.market_name[:30]} ({pos.age_minutes:.0f}m old)")
        
        # 2. Check exposure balance
        if self.positions:
            yes = sum(p.size for p in self.positions.values() if p.side == 'YES')
            no = sum(p.size for p in self.positions.values() if p.side == 'NO')
            total = yes + no
            if total > 0:
                yes_pct = yes / total
                if yes_pct > 0.80:
                    issues.append(f"Heavily tilted YES ({yes_pct:.0%})")
                    recommendations.append("Consider diversifying to NO side")
                elif yes_pct < 0.20:
                    issues.append(f"Heavily tilted NO ({1-yes_pct:.0%})")
                    recommendations.append("Consider diversifying to YES side")
        
        # 3. Check capital depletion
        if self.capital < 1.0:
            issues.append(f"Capital critically low: ${self.capital:.2f}")
        
        # 4. Check recent trade frequency
        recent_closes = [p for p in self.closed_positions if p.exit_time and 
                        (datetime.now() - datetime.fromisoformat(p.exit_time)).total_seconds() < 3600]
        if len(recent_closes) > 5:
            issues.append(f"High trade frequency: {len(recent_closes)} closes in last hour")
        
        # Determine status
        if issues:
            status = 'warning' if len(issues) < 3 else 'critical'
        else:
            status = 'healthy'
        
        return {
            'status': status,
            'timestamp': now,
            'open_positions': len(self.positions),
            'capital': self.capital,
            'issues': issues,
            'recommendations': recommendations,
            'consecutive_failures': self.consecutive_failures,
        }
    
    def record_health_failure(self):
        """Record consecutive health check failure"""
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_consecutive_failures:
            logger.error(f"🚨 {self.consecutive_failures} consecutive health failures — EMERGENCY PROTOCOL")
            return True  # Trigger emergency
        return False
    
    def reset_health(self):
        """Reset failure counter after successful operation"""
        self.consecutive_failures = 0
    
    # ═══════════════════════════════════════════
    # EMERGENCY PROTOCOLS
    # ═══════════════════════════════════════════
    
    def emergency_close_all(self) -> List[Position]:
        """Emergency close all open positions"""
        logger.warning("🚨 EMERGENCY CLOSING ALL POSITIONS")
        closed = []
        for pid, pos in list(self.positions.items()):
            # Close at current price (or mid if no price)
            exit_price = pos.current_price or pos.entry_price
            result = self.close_position(pid, exit_price, "EMERGENCY")
            if result:
                closed.append(result)
        
        logger.warning(f"🚨 Emergency closed {len(closed)} positions")
        return closed
