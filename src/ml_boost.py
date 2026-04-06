#!/usr/bin/env python3
"""
Luna ML Boost — Phase 1: Lightweight Confidence Enhancer

Philosophy:
- Rule-based system tetap primary (Kelly, EV, filters)
- ML hanya sebagai confidence booster/penalty (±0.03 max)
- Model: Logistic Regression (fast, transparent, $0 cost)
- Train otomatis setiap 50 trade atau 24h
- Cold start: ML weight = 0, gradual naik sesuai akurasi

Features:
- sentiment_score (from news)
- volume_24h (normalized)
- price_mid (current market price)
- spread_pct (bid/ask spread)
- liquidity (total depth)
- time_to_resolution_hours (duration remaining)
- market_age_hours (how long market existed)
- category_risk (risk profile per category)

Labels:
- 1 = YES side won
- 0 = NO side won

Output:
- ml_confidence (0-1): probability YES wins
- ml_adjustment (-0.03 to +0.03): adjustment to rule-based confidence
- ml_ready (bool): whether model has enough data
"""

import os
import json
import pickle
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
MODEL_PATH = os.path.join(DATA_DIR, 'ml_model.pkl')
METADATA_PATH = os.path.join(DATA_DIR, 'ml_metadata.json')


class MLBoost:
    """Lightweight ML confidence booster for rule-based system."""
    
    def __init__(self, db_memory=None):
        self.model = None
        self.metadata = self._load_metadata()
        self.db_memory = db_memory
        
        # Thresholds
        self.min_trades_for_training = 20  # Minimum trades before first train
        self.training_interval_trades = 50  # Retrain every 50 trades
        self.max_adjustment = 0.03  # Max ±adjustment to confidence
        self.maturity_threshold = 100  # Full weight at 100 trades
        
        # Load existing model if available
        self._load_model()
        
    def _load_metadata(self) -> Dict:
        """Load or initialize metadata."""
        try:
            if os.path.exists(METADATA_PATH):
                with open(METADATA_PATH, 'r') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"⚠️ ML metadata corrupt: {e}")
        
        return {
            'total_trades': 0,
            'last_trained': None,
            'train_count': 0,
            'accuracy_history': [],
            'model_ready': False,
            'weight': 0.0,  # How much to trust ML (0.0 to 1.0)
            'features': [
                'sentiment_score', 'volume_24h', 'price_mid',
                'spread_pct', 'liquidity', 'time_to_resolution_hours',
                'market_age_hours', 'category_risk'
            ]
        }
        
    def _load_model(self):
        """Load trained model from disk."""
        if not os.path.exists(MODEL_PATH):
            logger.info("🤖 ML model not found — cold start (weight = 0.0)")
            return
        
        try:
            with open(MODEL_PATH, 'rb') as f:
                self.model = pickle.load(f)
            
            if self.metadata.get('model_ready'):
                current_weight = self._calculate_weight()
                logger.info(f"🤖 ML model loaded | Accuracy: {self._get_latest_accuracy():.1%} | Weight: {current_weight:.2f}")
            else:
                logger.info("🤖 ML model loaded but not ready yet")
                
        except (pickle.UnpicklingError, IOError) as e:
            logger.warning(f"⚠️ ML model corrupt, starting fresh: {e}")
            self.model = None
            
    def _save_model(self):
        """Save model and metadata to disk."""
        os.makedirs(DATA_DIR, exist_ok=True)
        
        try:
            with open(MODEL_PATH, 'wb') as f:
                pickle.dump(self.model, f)
            
            with open(METADATA_PATH, 'w') as f:
                json.dump(self.metadata, f, indent=2, default=str)
                
            logger.info(f"💾 ML model saved | Train #{self.metadata['train_count']}")
        except IOError as e:
            logger.error(f"❌ Failed to save ML model: {e}")
            
    def _calculate_weight(self) -> float:
        """Calculate how much to trust ML based on maturity."""
        if not self.metadata.get('model_ready'):
            return 0.0
        
        trades = self.metadata['total_trades']
        if trades >= self.maturity_threshold:
            return 1.0  # Full weight
        
        # Gradual increase from 0 to 1.0
        return min(1.0, trades / self.maturity_threshold)
    
    def _get_latest_accuracy(self) -> float:
        """Get latest model accuracy."""
        if self.metadata['accuracy_history']:
            return self.metadata['accuracy_history'][-1]
        return 0.5  # Default when no data
        
    def _normalize_features(self, raw_features: Dict) -> np.ndarray:
        """Normalize features to 0-1 range for model input."""
        # Hardcoded normalization based on expected ranges
        normalized = np.array([
            max(0.0, min(1.0, raw_features.get('sentiment_score', 0.5))),
            min(1.0, raw_features.get('volume_24h', 0) / 100000),  # Cap at $100k
            raw_features.get('price_mid', 0.5),  # Already 0-1
            min(1.0, raw_features.get('spread_pct', 0.01) / 0.05),  # Cap at 5%
            min(1.0, raw_features.get('liquidity', 0) / 100000),  # Cap at $100k
            min(1.0, raw_features.get('time_to_resolution_hours', 168) / (30 * 24)),  # Cap at 30 days
            min(1.0, raw_features.get('market_age_hours', 24) / (7 * 24)),  # Cap at 7 days
            max(0.0, min(1.0, raw_features.get('category_risk', 0.5))),
        ])
        
        return normalized.reshape(1, -1)
        
    def predict(self, market_features: Dict) -> Dict:
        """
        Predict YES probability and calculate confidence adjustment.
        
        Args:
            market_features: Dict with feature values for the market
            
        Returns:
            Dict with ml_confidence, ml_adjustment, ml_ready
        """
        if self.model is None or not self.metadata.get('model_ready'):
            return {
                'ml_confidence': 0.5,  # Neutral when no model
                'ml_adjustment': 0.0,
                'ml_ready': False,
                'weight': 0.0
            }
        
        try:
            features = self._normalize_features(market_features)
            prob_yes = float(self.model.predict_proba(features)[0][1])
            
            # ML confidence is probability YES wins
            ml_confidence = prob_yes
            
            # Calculate adjustment: difference from neutral (0.5)
            deviation = ml_confidence - 0.5
            
            # Scale by current weight (starts at 0, grows to 1.0)
            current_weight = self._calculate_weight()
            ml_adjustment = deviation * current_weight * self.max_adjustment * 2  # Scale to ±0.03 max
            
            return {
                'ml_confidence': ml_confidence,
                'ml_adjustment': ml_adjustment,
                'ml_ready': True,
                'weight': current_weight
            }
            
        except Exception as e:
            logger.warning(f"⚠️ ML prediction failed: {e}")
            return {
                'ml_confidence': 0.5,
                'ml_adjustment': 0.0,
                'ml_ready': False,
                'weight': 0.0
            }
            
    def record_trade(self, market_id: str, features: Dict, outcome: Optional[int] = None):
        """
        Record a trade for future training.
        
        Args:
            market_id: Unique market identifier
            features: Feature values used for prediction
            outcome: 1 if YES won, 0 if NO won (None if unresolved)
        """
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        
        trades_path = os.path.join(DATA_DIR, 'ml_trades.jsonl')
        
        trade_record = {
            'market_id': market_id,
            'features': features,
            'outcome': outcome,
            'timestamp': datetime.now().isoformat()
        }
        
        with open(trades_path, 'a') as f:
            f.write(json.dumps(trade_record) + '\n')
        
        if outcome is not None:
            self.metadata['total_trades'] += 1
            logger.info(f"📊 Recorded trade #{self.metadata['total_trades']} | Market: {market_id}")
            
            # Check if we should retrain
            if self._should_train():
                self.train()
                
    def _should_train(self) -> bool:
        """Check if conditions are right for training."""
        trades = self.metadata['total_trades']
        last_trained = self.metadata.get('last_trained')
        
        # First train ever
        if trades >= self.min_trades_for_training and not self.metadata.get('model_ready'):
            return True
        
        # Retraining interval
        if self.metadata.get('model_ready') and trades % self.training_interval_trades == 0:
            return True
            
        # Time-based retrain (24h)
        if last_trained:
            last_train_dt = datetime.fromisoformat(last_trained)
            if datetime.now() - last_train_dt > timedelta(hours=24) and trades > self.min_trades_for_training:
                return True
                
        return False
        
    def train(self) -> bool:
        """Train model on historical trade data."""
        trades_path = os.path.join(DATA_DIR, 'ml_trades.jsonl')
        
        if not os.path.exists(trades_path):
            logger.warning("⚠️ No trade data for training")
            return False
        
        # Load trades
        trades = []
        with open(trades_path, 'r') as f:
            for line in f:
                trade = json.loads(line)
                # Only use resolved trades
                if trade.get('outcome') is not None:
                    trades.append(trade)
        
        if len(trades) < self.min_trades_for_training:
            logger.warning(f"⚠️ Not enough data for training: {len(trades)}/{self.min_trades_for_training}")
            return False
        
        # Prepare dataset
        X, y = [], []
        for trade in trades:
            features = trade['features']
            outcome = trade['outcome']
            
            normalized = self._normalize_features(features)
            X.append(normalized.flatten())
            y.append(outcome)
        
        X = np.array(X)
        y = np.array(y)
        
        # Train Logistic Regression (no sklearn import at top for safety)
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.model_selection import cross_val_score
            
            model = LogisticRegression(
                max_iter=1000,
                C=1.0,
                solver='lbfgs'
            )
            
            # Cross-validation for accuracy
            if len(y) >= 10:
                cv_scores = cross_val_score(model, X, y, cv=min(5, len(y)//2))
                accuracy = cv_scores.mean()
            else:
                model.fit(X, y)
                accuracy = model.score(X, y)
            
            # Final train on all data
            model.fit(X, y)
            
            self.model = model
            self.metadata['model_ready'] = True
            self.metadata['last_trained'] = datetime.now().isoformat()
            self.metadata['train_count'] += 1
            self.metadata['accuracy_history'].append(accuracy)
            
            # Keep only last 10 accuracy records
            if len(self.metadata['accuracy_history']) > 10:
                self.metadata['accuracy_history'] = self.metadata['accuracy_history'][-10:]
            
            self._save_model()
            
            weight = self._calculate_weight()
            logger.info(f"🤖 ML Model Trained #{self.metadata['train_count']} | "
                       f"Accuracy: {accuracy:.1%} | "
                       f"Trades: {len(trades)} | "
                       f"Weight: {weight:.2f}")
            
            return True
            
        except ImportError:
            logger.warning("⚠️ scikit-learn not installed — install with: pip install scikit-learn")
            return False
        except Exception as e:
            logger.error(f"❌ ML training failed: {e}")
            return False
            
    def get_status(self) -> Dict:
        """Get ML module status for reporting."""
        return {
            'ready': self.metadata.get('model_ready', False),
            'total_trades': self.metadata['total_trades'],
            'train_count': self.metadata['train_count'],
            'accuracy': self._get_latest_accuracy() if self.metadata['accuracy_history'] else 0.0,
            'weight': self._calculate_weight(),
            'last_trained': self.metadata.get('last_trained'),
            'model_exists': os.path.exists(MODEL_PATH)
        }


# Quick test
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    boost = MLBoost()
    
    # Simulate cold start
    print("\n🌙 ML Boost Status (Cold Start):")
    print(json.dumps(boost.get_status(), indent=2))
    
    # Test prediction without model
    test_features = {
        'sentiment_score': 0.7,
        'volume_24h': 50000,
        'price_mid': 0.65,
        'trade_count': 150,
        'price_volatility': 0.02,
        'time_to_resolution_hours': 48,
        'market_age_hours': 120,
        'category_risk': 0.3
    }
    
    result = boost.predict(test_features)
    print(f"\n📊 Prediction test: {result}")
    
    print("\n✅ ML Boost module ready")
