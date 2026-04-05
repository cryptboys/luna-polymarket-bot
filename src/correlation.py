# Correlation Engine
# Phase 4: Prevent overexposure to correlated markets
# Detects when multiple positions are effectively the same bet

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


# Manually defined correlation groups
# When you have positions in multiple markets from same group = higher risk
CORRELATION_GROUPS = {
    # US Elections — all correlated
    'us_elections': [
        'president', 'election', 'trump', 'biden', 'harris',
        'republican', 'democrat', 'senate', 'house', 'congress'
    ],
    # Crypto — all move together
    'crypto': [
        'bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'sol',
        'crypto', 'defi', 'binance', 'sec crypto', 'etf'
    ],
    # Fed/Monetary Policy
    'fed': [
        'fed rate', 'interest rate', 'fomc', 'jerome powell',
        'inflation', 'cpi', 'recession'
    ],
    # Geopolitics
    'geopolitics': [
        'ukraine', 'russia', 'china', 'taiwan', 'israel',
        'nato', 'sanctions', 'trade war'
    ],
    # Sports (same event)
    'sports_nfl': ['nfl', 'super bowl', 'chiefs', 'eagles', '49ers'],
    'sports_nba': ['nba', 'lakers', 'celtics', 'warriors', 'finals'],
}

# Markets in same group share exposure
CORRELATION_EXPOSURE_LIMIT = 0.40  # Max 40% of portfolio in one group


class CorrelationEngine:
    """
    Detects correlated markets and prevents overexposure.
    
    Why: If you have 3 positions in US election markets,
    you're not diversified — one political event affects all three.
    """
    
    def __init__(self):
        self.groups = CORRELATION_GROUPS.copy()
        self._category_cache: Dict[str, str] = {}
    
    def classify_market(self, market_name: str, category: str = None) -> str:
        """
        Classify a market into a correlation group.
        Returns the group name or 'uncorrelated'.
        """
        cache_key = market_name.lower()
        if cache_key in self._category_cache:
            return self._category_cache[cache_key]
        
        name_lower = market_name.lower()
        
        # Check each correlation group
        for group, keywords in self.groups.items():
            for keyword in keywords:
                if keyword in name_lower:
                    self._category_cache[cache_key] = group
                    return group
        
        # Fallback to category
        if category:
            cat_lower = category.lower()
            for group, keywords in self.groups.items():
                if any(kw in cat_lower for kw in keywords):
                    self._category_cache[cache_key] = group
                    return group
        
        self._category_cache[cache_key] = 'uncorrelated'
        return 'uncorrelated'
    
    def get_group_exposure(self, positions: List[Dict]) -> Dict[str, Dict]:
        """
        Calculate exposure per correlation group.
        
        positions: list of dicts with 'market_name', 'size', 'side'
        
        Returns: {group: {total_exposure, positions, percentage}}
        """
        total_exposure = sum(p.get('size', 0) for p in positions)
        if total_exposure <= 0:
            return {}
        
        group_data: Dict[str, Dict] = {}
        
        for pos in positions:
            market_name = pos.get('market_name', '')
            category = pos.get('category', '')
            size = pos.get('size', 0)
            
            group = self.classify_market(market_name, category)
            
            if group not in group_data:
                group_data[group] = {
                    'total_exposure': 0,
                    'positions': [],
                    'percentage': 0,
                    'risk_level': 'low',
                }
            
            group_data[group]['total_exposure'] += size
            group_data[group]['positions'].append({
                'name': market_name[:50],
                'size': size,
                'side': pos.get('side', 'UNKNOWN'),
            })
        
        # Calculate percentages and risk
        for group, data in group_data.items():
            data['percentage'] = (data['total_exposure'] / total_exposure) * 100 if total_exposure > 0 else 0
            
            if data['percentage'] > 60:
                data['risk_level'] = 'critical'
            elif data['percentage'] > 40:
                data['risk_level'] = 'high'
            elif data['percentage'] > 25:
                data['risk_level'] = 'medium'
            else:
                data['risk_level'] = 'low'
        
        return group_data
    
    def check_concentration(self, positions: List[Dict]) -> Tuple[bool, str]:
        """
        Check if any correlation group is over-concentrated.
        
        Returns: (is_safe, warning_message)
        """
        group_data = self.get_group_exposure(positions)
        
        for group, data in group_data.items():
            if group == 'uncorrelated':
                continue
            
            if data['percentage'] > CORRELATION_EXPOSURE_LIMIT * 100:
                positions_list = ", ".join(p['name'] for p in data['positions'][:3])
                return False, (
                    f"⚠️ Overexposed to {group}: {data['percentage']:.0f}% of portfolio "
                    f"(${data['total_exposure']:.2f}). "
                    f"Positions: {positions_list}. "
                    f"Max allowed: {CORRELATION_EXPOSURE_LIMIT*100:.0f}%"
                )
        
        return True, "Correlation risk OK"
    
    def should_open_position(self, market_name: str, category: str, 
                            position_size: float, current_positions: List[Dict]) -> Tuple[bool, str]:
        """
        Check if opening a new position would create dangerous correlation.
        
        Returns: (can_open, reason)
        """
        new_group = self.classify_market(market_name, category)
        
        if new_group == 'uncorrelated':
            return True, "Uncorrelated — no concentration risk"
        
        # Calculate what exposure would be after adding new position
        test_positions = current_positions + [{
            'market_name': market_name,
            'category': category,
            'size': position_size,
            'side': 'YES',
        }]
        
        is_safe, warning = self.check_concentration(test_positions)
        
        if is_safe:
            return True, f"New position in {new_group} is within limits"
        else:
            return False, f"Would exceed {new_group} concentration limit: {warning}"
    
    def get_correlation_report(self, positions: List[Dict]) -> str:
        """Generate a human-readable correlation report"""
        group_data = self.get_group_exposure(positions)
        
        if not group_data:
            return "📊 No positions to analyze"
        
        lines = ["📊 CORRELATION EXPOSURE REPORT", "=" * 40]
        
        for group, data in sorted(group_data.items(), key=lambda x: x[1]['total_exposure'], reverse=True):
            emoji = {'critical': '🚨', 'high': '⚠️', 'medium': '📋', 'low': '✅', 'uncorrelated': '🔵'}.get(data['risk_level'], '📋')
            lines.append(f"{emoji} {group.upper()}")
            lines.append(f"   Exposure: ${data['total_exposure']:.2f} ({data['percentage']:.0f}%)")
            lines.append(f"   Risk: {data['risk_level']}")
            for pos in data['positions']:
                lines.append(f"   → {pos['side']} ${pos['size']:.2f}: {pos['name']}")
            lines.append("")
        
        return "\n".join(lines)
