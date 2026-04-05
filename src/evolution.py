# Online Learning & Adaptation Module
# Phase 3: The bot learns from its own PnL to optimize strategy weights.
# It doesn't just follow rules; it EVOLVES them.

import os
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    'liquidity': 0.15,
    'volume': 0.15,
    'spread': 0.10,
    'momentum': 0.20,
    'price_position': 0.10,
    'time_decay': 0.10,
    'category': 0.10,
    'market_age': 0.10,
}

@dataclass
class EvolutionState:
    """Stores the current evolved state of the strategy"""
    weights: Dict[str, float]
    calibration_factor: float  # Multiplier for confidence (e.g. 1.1 means we underestimate)
    category_adjustments: Dict[str, float]  # Category specific EV bumps
    last_update: str = ""
    total_trades_analyzed: int = 0

class EvolutionEngine:
    """
    Analyzes past trade history to adjust strategy parameters.
    Runs periodically (e.g., every 24h or every 50 trades).
    """
    
    def __init__(self, db_path: str, strategy_instance):
        self.db_path = db_path
        self.strategy = strategy_instance
        self.state_file = os.path.join(os.path.dirname(db_path), "evolution_state.json")
        self.state = self._load_state()

    def _load_state(self) -> EvolutionState:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    return EvolutionState(**data)
            except Exception as e:
                logger.error(f"Failed to load evolution state: {e}")
        
        # Default state
        return EvolutionState(
            weights=DEFAULT_WEIGHTS.copy(),
            calibration_factor=1.0,
            category_adjustments={},
            last_update=datetime.now().isoformat(),
            total_trades_analyzed=0
        )

    def save_state(self):
        self.state.last_update = datetime.now().isoformat()
        with open(self.state_file, 'w') as f:
            json.dump(asdict(self.state), f, indent=2)
        logger.info(f"💾 Evolution state saved (Trades: {self.state.total_trades_analyzed})")

    def run_analysis(self, min_trades: int = 20):
        """
        Main loop:
        1. Fetch closed trades.
        2. Check if enough data.
        3. Analyze feature importance.
        4. Update weights & calibration.
        5. Save.
        """
        trades = self._fetch_recent_trades()
        if len(trades) < min_trades:
            logger.info(f"🧠 Evolution skipped: Only {len(trades)} trades (min {min_trades})")
            return
        
        # Only analyze new trades since last run
        new_trades_count = len(trades) - self.state.total_trades_analyzed
        if new_trades_count <= 0:
             logger.info("🧠 Evolution skipped: No new trades data")
             return

        logger.info(f"🧠 Learning from {len(trades)} trades...")
        
        # 1. Adjust Weights based on correlation with Win/Loss
        self._adjust_weights(trades)
        
        # 2. Calibrate confidence (Is the bot over/under-confident?)
        self._calibrate_confidence(trades)
        
        # 3. Category adjustments
        self._adjust_categories(trades)
        
        # Update counter
        self.state.total_trades_analyzed = len(trades)
        self.save_state()
        
        # Push changes to Strategy instance
        self._apply_to_strategy()

    def _fetch_recent_trades(self) -> List[Dict]:
        """Fetch closed trades with their scoring data"""
        if not os.path.exists(self.db_path):
            return []
            
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get scoring_json (where we stored individual factor scores)
            cursor.execute("""
                SELECT action, actual_pnl, confidence, scoring_json 
                FROM trades 
                WHERE status = 'CLOSED' AND scoring_json IS NOT NULL
                ORDER BY timestamp DESC
            """)
            
            trades = []
            for row in cursor.fetchall():
                try:
                    scores = json.loads(row['scoring_json'])
                    trades.append({
                        'won': row['actual_pnl'] > 0 if row['actual_pnl'] is not None else False,
                        'predicted_conf': row['confidence'],
                        'scores': scores
                    })
                except:
                    continue
            
            conn.close()
            return trades
        except Exception as e:
            logger.error(f"Error fetching trades for evolution: {e}")
            return []

    def _adjust_weights(self, trades: List[Dict]):
        """
        Analyze which factors correlated with winning.
        Logic: 
        Calculate average score of Winners vs Losers for each factor.
        If Winners have much higher 'momentum' score than Losers -> Increase momentum weight.
        """
        
        factor_performance = {k: {'wins_score': 0.0, 'win_count': 0, 'loss_score': 0.0, 'loss_count': 0} for k in DEFAULT_WEIGHTS}
        
        for t in trades:
            won = t['won']
            scores = t['scores']
            
            for factor in DEFAULT_WEIGHTS:
                score = scores.get(factor, 0.5)
                if won:
                    factor_performance[factor]['wins_score'] += score
                    factor_performance[factor]['win_count'] += 1
                else:
                    factor_performance[factor]['loss_score'] += score
                    factor_performance[factor]['loss_count'] += 1
        
        # Calculate delta
        deltas = {}
        for factor, perf in factor_performance.items():
            if perf['win_count'] > 0 and perf['loss_count'] > 0:
                avg_win = perf['wins_score'] / perf['win_count']
                avg_loss = perf['loss_score'] / perf['loss_count']
                # Difference indicates predictive power
                deltas[factor] = avg_win - avg_loss
            else:
                deltas[factor] = 0.0

        # Adjust weights: Add small portion of delta to existing weight
        # Then renormalize so sum(weights) = 1.0
        learning_rate = 0.1 # Slow learning to avoid overfitting
        
        new_weights = {}
        for factor in DEFAULT_WEIGHTS:
            current_w = self.state.weights.get(factor, DEFAULT_WEIGHTS[factor])
            delta = deltas.get(factor, 0.0)
            
            # If factor distinguishes winners (delta > 0), increase weight
            new_w = current_w + (learning_rate * delta)
            new_weights[factor] = max(0.05, min(0.30, new_w)) # Clamp between 5% and 30%
            
        # Renormalize
        total = sum(new_weights.values())
        for k in new_weights:
            new_weights[k] = new_weights[k] / total
            
        self.state.weights = new_weights
        logger.info(f"⚖️ Weights adjusted based on performance")
        for k, v in new_weights.items():
            logger.info(f"   {k}: {v:.2f}")

    def _calibrate_confidence(self, trades: List[Dict]):
        """
        Compare predicted confidence vs actual win rate.
        If bot predicts 70% but wins 80% -> Needs calibration UP (factor > 1.0).
        If bot predicts 70% but wins 60% -> Needs calibration DOWN (factor < 1.0).
        """
        
        # Group trades by confidence buckets (e.g. 0.5-0.6, 0.6-0.7...)
        buckets = {}
        for t in trades:
            conf = t['predicted_conf']
            bucket = int(conf * 10) / 10.0 # Floor to 1 decimal
            
            if bucket not in buckets:
                buckets[bucket] = {'wins': 0, 'total': 0}
            
            buckets[bucket]['total'] += 1
            if t['won']:
                buckets[bucket]['wins'] += 1
                
        # Calculate overall calibration factor
        # We want: Weighted Average of (Actual_Win_Rate / Predicted_Confidence)
        total_predicted_proba = 0
        total_actual_wins = 0
        
        for conf_range, stats in buckets.items():
            if stats['total'] > 0:
                actual_rate = stats['wins'] / stats['total']
                total_actual_wins += actual_rate * stats['total']
                total_predicted_proba += conf_range * stats['total'] # Approx center
        
        if total_predicted_proba > 0:
            calibration = total_actual_wins / total_predicted_proba
            # Smooth the adjustment
            old_cal = self.state.calibration_factor
            new_cal = (old_cal * 0.7) + (calibration * 0.3) # 70% history, 30% new data
            self.state.calibration_factor = max(0.8, min(1.3, new_cal))
            
            logger.info(f"🎯 Calibration: {new_cal:.2f}x (Was {old_cal:.2f}, Measured {calibration:.2f})")
        else:
            logger.warning("No calibration data available")

    def _adjust_categories(self, trades: List[Dict]):
        """
        If a specific category consistently loses money, add a penalty to its EV.
        """
        cat_pnl = {}
        # Note: Category isn't explicitly in trades table in this version, 
        # usually inferred from market_id or name.
        # For this Phase 3 impl, we'll look at Market ID patterns or just skip detailed category analysis
        # unless we store category in DB.
        # Let's assume for now we track 'market_name'. If it contains 'crypto', 'politics', etc.
        
        for t in trades:
            # Simple categorization based on context or metadata if available
            # Since we don't have category in this snippet, we'll skip detailed category adjustment 
            # to avoid errors. 
            pass

    def _apply_to_strategy(self):
        """Push new weights/calibration to the running Strategy instance"""
        if self.strategy:
            self.strategy.WEIGHTS = self.state.weights
            logger.info(f"✅ Applied evolved weights to Strategy")

    @property
    def adjustment_report(self) -> str:
        w = self.state.weights
        return (
            f"🧠 EVOLUTION REPORT\n"
            f"Weights: {json.dumps({k: f'{v:.2f}' for k, v in w.items()})}\n"
            f"Calibration: {self.state.calibration_factor:.2f}x"
        )

    def _apply_to_strategy(self):
        """Push new weights to running Strategy instance"""
        if self.strategy and hasattr(self.strategy, 'WEIGHTS'):
            if self.state.weights != self.strategy.WEIGHTS:
                self.strategy.WEIGHTS = self.state.weights
                logger.info(f"🔄 Strategy weights updated from Evolution Engine")
