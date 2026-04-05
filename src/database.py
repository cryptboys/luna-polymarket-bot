# Database & Memory Management for Luna Bot — Phase 2
# Upgraded: market_score, kelly_fraction, scoring breakdown, context manager

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class LunaMemory:
    """
    Persistent memory for Luna Bot
    Stores: trades (with scoring breakdown), evolution, market history
    """
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base, 'data', 'luna_memory.db')
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_database()
    
    @contextmanager
    def _conn(self):
        """Context manager for safe DB connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize all tables + migrate existing schema"""
        with self._conn() as conn:
            cursor = conn.cursor()
            
            # Trades table (with scoring breakdown — Phase 2)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    date TEXT,
                    market_id TEXT,
                    market_name TEXT,
                    action TEXT,
                    side TEXT,
                    size REAL,
                    price REAL,
                    confidence REAL,
                    market_score REAL,
                    kelly_fraction REAL,
                    scoring_json TEXT,
                    expected_return REAL,
                    actual_pnl REAL,
                    status TEXT DEFAULT 'OPEN',
                    exit_price REAL,
                    exit_time TEXT,
                    lesson_learned TEXT,
                    phase INTEGER,
                    trade_type TEXT DEFAULT 'paper'
                )
            ''')
            
            # Add new columns to existing tables (migration safety)
            columns_to_add = [
                ('trades', 'market_score', 'REAL DEFAULT 0'),
                ('trades', 'kelly_fraction', 'REAL DEFAULT 0'),
                ('trades', 'scoring_json', 'TEXT'),
                ('trades', 'trade_type', 'TEXT DEFAULT \'paper\''),
            ]
            for table, col, type_def in columns_to_add:
                try:
                    cursor.execute(f'ALTER TABLE {table} ADD COLUMN {col} {type_def}')
                except sqlite3.OperationalError:
                    pass  # Column already exists
            
            # Daily evolution
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS evolution (
                    date TEXT PRIMARY KEY,
                    starting_capital REAL,
                    ending_capital REAL,
                    total_trades INTEGER,
                    winning_trades INTEGER,
                    losing_trades INTEGER,
                    win_rate REAL,
                    roi_percent REAL,
                    lessons TEXT,
                    phase INTEGER
                )
            ''')
            
            # Market memory (with scoring history)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS market_memory (
                    market_id TEXT PRIMARY KEY,
                    first_seen TEXT,
                    last_analyzed TEXT,
                    total_signals INTEGER DEFAULT 0,
                    successful_signals INTEGER DEFAULT 0,
                    avg_confidence REAL,
                    avg_score REAL DEFAULT 0,
                    market_category TEXT,
                    avg_kelly REAL DEFAULT 0
                )
            ''')
            
            # Add avg_score/avg_kelly columns if migrating
            try:
                cursor.execute('ALTER TABLE market_memory ADD COLUMN avg_score REAL DEFAULT 0')
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute('ALTER TABLE market_memory ADD COLUMN avg_kelly REAL DEFAULT 0')
            except sqlite3.OperationalError:
                pass
            
            # Signal history (track every signal, even HOLD)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS signal_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    market_id TEXT,
                    market_name TEXT,
                    market_category TEXT,
                    action TEXT,
                    confidence REAL,
                    market_score REAL,
                    kelly_fraction REAL,
                    recommended_side TEXT,
                    phase INTEGER
                )
            ''')
            
            conn.commit()
        
        logger.info(f"✅ Database initialized: {self.db_path}")
    
    def load_capital_into(self, bot):
        """Load previous session capital and stats into bot instance"""
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                
                # Get latest capital from evolution
                cursor.execute('SELECT ending_capital FROM evolution ORDER BY date DESC LIMIT 1')
                result = cursor.fetchone()
                if result and result[0]:
                    bot.current_capital = result[0]
                    logger.info(f"📊 Loaded capital from memory: ${bot.current_capital:.2f}")
                
                # Get phase from latest evolution
                cursor.execute('SELECT phase FROM evolution ORDER BY date DESC LIMIT 1')
                phase_result = cursor.fetchone()
                if phase_result and phase_result[0]:
                    bot.phase = phase_result[0]
                    logger.info(f"🚀 Loaded phase: {bot.phase}")
                
                # Win rate stats
                cursor.execute('SELECT COUNT(*) FROM trades WHERE status = ? AND actual_pnl > 0', ('CLOSED',))
                wins = cursor.fetchone()[0]
                cursor.execute('SELECT COUNT(*) FROM trades WHERE status = ?', ('CLOSED',))
                total = cursor.fetchone()[0]
                
                if total > 0:
                    win_rate = wins / total
                    logger.info(f"📈 Historical Win Rate: {win_rate:.1%} ({wins}/{total})")
                    
                    if win_rate > 0.70 and bot.phase < 4 and total >= 10:
                        logger.info(f"🚀 Win rate >70% with {total} trades — ready for Phase {bot.phase + 1}")
        except Exception as e:
            logger.warning(f"⚠️ Could not load memory: {e}")
    
    def log_paper_trade(self, trade_data: Dict[str, Any]) -> int:
        """Log a paper trade"""
        trade_data['trade_type'] = 'paper'
        return self._log_trade(trade_data)
    
    def log_live_trade(self, trade_data: Dict[str, Any]) -> int:
        """Log a live trade"""
        trade_data['trade_type'] = 'live'
        return self._log_trade(trade_data)
    
    def log_signal(self, market_id: str, market_name: str, category: str, 
                   action: str, confidence: float, market_score: float,
                   kelly_fraction: float, recommended_side: str, phase: int):
        """Log every signal (even HOLD) for analysis"""
        try:
            with self._conn() as conn:
                conn.execute('''
                    INSERT INTO signal_log 
                    (market_id, market_name, market_category, action, 
                     confidence, market_score, kelly_fraction, recommended_side, phase)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (market_id, market_name, category, action, 
                      confidence, market_score, kelly_fraction, recommended_side, phase))
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to log signal: {e}")
    
    def _log_trade(self, trade_data: Dict[str, Any]) -> int:
        """Internal trade logging"""
        try:
            with self._conn() as conn:
                scoring_json = json.dumps(trade_data.get('scoring', {}))
                
                cursor = conn.execute('''
                    INSERT INTO trades 
                    (date, market_id, market_name, action, side, size, price, 
                     confidence, market_score, kelly_fraction, scoring_json,
                     expected_return, phase, trade_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    datetime.now().strftime('%Y-%m-%d'),
                    trade_data.get('market_id'),
                    trade_data.get('market_name'),
                    trade_data.get('action'),
                    trade_data.get('side'),
                    trade_data.get('size'),
                    trade_data.get('price'),
                    trade_data.get('confidence'),
                    trade_data.get('market_score', 0),
                    trade_data.get('kelly_fraction', 0),
                    scoring_json,
                    trade_data.get('expected_return'),
                    trade_data.get('phase', 1),
                    trade_data.get('trade_type', 'paper')
                ))
                
                conn.commit()
                trade_id = cursor.lastrowid
                logger.info(f"📝 Trade #{trade_id} logged: {trade_data.get('action')} ${trade_data.get('size', 0):.2f} {trade_data.get('side', '')}")
                return trade_id
        except Exception as e:
            logger.error(f"Failed to log trade: {e}")
            return -1
    
    def close_trade(self, trade_id: int, exit_price: float, pnl: float, lesson: str = ''):
        """Close a trade and record PnL"""
        try:
            with self._conn() as conn:
                conn.execute('''
                    UPDATE trades 
                    SET status = 'CLOSED', exit_price = ?, exit_time = ?,
                        actual_pnl = ?, lesson_learned = ?
                    WHERE id = ?
                ''', (exit_price, datetime.now().isoformat(), pnl, lesson, trade_id))
                conn.commit()
                logger.info(f"✅ Trade #{trade_id} closed — PnL: ${pnl:+.2f}")
        except Exception as e:
            logger.error(f"Failed to close trade: {e}")
    
    def get_open_trades(self) -> List[Dict]:
        """Get all open trades"""
        with self._conn() as conn:
            cursor = conn.execute('SELECT * FROM trades WHERE status = ? ORDER BY timestamp DESC', ('OPEN',))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_trade_history(self, days: int = 30, trade_type: str = None) -> List[Dict]:
        """Get trade history"""
        with self._conn() as conn:
            since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            if trade_type:
                cursor = conn.execute(
                    'SELECT * FROM trades WHERE date >= ? AND trade_type = ? ORDER BY timestamp DESC',
                    (since, trade_type)
                )
            else:
                cursor = conn.execute(
                    'SELECT * FROM trades WHERE date >= ? ORDER BY timestamp DESC',
                    (since,)
                )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_trading_stats(self, date_filter: str = None) -> Dict[str, Any]:
        """
        Get trading statistics.
        If date_filter is a specific date (YYYY-MM-DD), return today's stats.
        If None, return all-time stats.
        """
        with self._conn() as conn:
            cursor = conn.cursor()
            
            if date_filter:
                # Single day stats
                cursor.execute('''
                    SELECT COUNT(*) as total,
                           SUM(CASE WHEN actual_pnl > 0 THEN 1 ELSE 0 END) as wins,
                           SUM(CASE WHEN actual_pnl < 0 THEN 1 ELSE 0 END) as losses,
                           COALESCE(SUM(actual_pnl), 0) as pnl
                    FROM trades 
                    WHERE date = ? AND status = 'CLOSED'
                ''', (date_filter,))
            else:
                # All-time stats
                cursor.execute('''
                    SELECT COUNT(*) as total,
                           SUM(CASE WHEN actual_pnl > 0 THEN 1 ELSE 0 END) as wins,
                           SUM(CASE WHEN actual_pnl < 0 THEN 1 ELSE 0 END) as losses,
                           COALESCE(SUM(actual_pnl), 0) as pnl
                    FROM trades 
                    WHERE status = 'CLOSED'
                ''')
            
            row = cursor.fetchone()
            total = row['total'] or 0
            wins = row['wins'] or 0
            losses = row['losses'] or 0
            pnl = row['pnl'] or 0
            
            win_rate = (wins / total) if total > 0 else 0
            
            # Get current capital from evolution or trades
            cursor.execute('SELECT ending_capital FROM evolution ORDER BY date DESC LIMIT 1')
            cap_row = cursor.fetchone()
            capital = cap_row['ending_capital'] if cap_row and cap_row['ending_capital'] else 0
            
            roi = (pnl / capital * 100) if capital > 0 else 0
            
            return {
                'total_trades': total,
                'winning_trades': wins,
                'losing_trades': losses,
                'total_closed': total,
                'win_rate': win_rate,
                'pnl': pnl,
                'roi': roi,
                'capital': capital,
            }
    
    def save_daily_evolution(self, data: Dict[str, Any]):
        """Save daily evolution data"""
        try:
            with self._conn() as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO evolution 
                    (date, starting_capital, ending_capital, total_trades, 
                     winning_trades, losing_trades, win_rate, roi_percent, lessons, phase)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data.get('date'),
                    data.get('starting_capital'),
                    data.get('ending_capital'),
                    data.get('total_trades'),
                    data.get('winning_trades'),
                    data.get('losing_trades'),
                    data.get('win_rate'),
                    data.get('roi_percent'),
                    json.dumps(data.get('lessons', [])),
                    data.get('phase')
                ))
                conn.commit()
                logger.info(f"📈 Daily evolution saved: {data.get('date')}")
        except Exception as e:
            logger.error(f"Failed to save evolution: {e}")
    
    def update_market_memory(self, market_id: str, category: str, 
                             signal_success: bool, score: float = 0, kelly: float = 0):
        """Update market-specific memory with score tracking"""
        try:
            with self._conn() as conn:
                conn.execute('''
                    INSERT INTO market_memory 
                    (market_id, first_seen, last_analyzed, total_signals, 
                     successful_signals, market_category, avg_score, avg_kelly)
                    VALUES (?, ?, ?, 1, ?, ?, ?, ?)
                    ON CONFLICT(market_id) DO UPDATE SET
                        last_analyzed = ?,
                        total_signals = total_signals + 1,
                        successful_signals = successful_signals + ?,
                        avg_score = CASE WHEN total_signals > 0 
                            THEN ((avg_score * total_signals) + ?) / (total_signals + 1) 
                            ELSE ? END,
                        avg_kelly = CASE WHEN total_signals > 0 
                            THEN ((avg_kelly * total_signals) + ?) / (total_signals + 1) 
                            ELSE ? END
                ''', (
                    market_id, datetime.now().isoformat(), datetime.now().isoformat(),
                    1 if signal_success else 0, category, score, kelly,
                    datetime.now().isoformat(),
                    1 if signal_success else 0, score, score, kelly, kelly
                ))
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to update market memory: {e}")
    
    def get_market_memory(self, market_id: str) -> Optional[Dict]:
        """Get memory for specific market"""
        try:
            with self._conn() as conn:
                cursor = conn.execute(
                    'SELECT * FROM market_memory WHERE market_id = ?', (market_id,)
                )
                row = cursor.fetchone()
                if row:
                    data = dict(row)
                    if data['total_signals'] > 0:
                        data['win_rate'] = data['successful_signals'] / data['total_signals']
                    else:
                        data['win_rate'] = 0
                    return data
        except Exception as e:
            logger.warning(f"Failed to get market memory: {e}")
        return None
    
    def get_lessons_learned(self, limit: int = 10) -> List[str]:
        """Extract lessons from past trades"""
        with self._conn() as conn:
            cursor = conn.execute('''
                SELECT lesson_learned FROM trades 
                WHERE lesson_learned IS NOT NULL AND lesson_learned != ''
                ORDER BY timestamp DESC LIMIT ?
            ''', (limit,))
            return [row[0] for row in cursor.fetchall() if row[0]]
    
    def get_signal_accuracy(self, days: int = 30) -> Dict[str, float]:
        """Get signal accuracy by category"""
        with self._conn() as conn:
            since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            cursor = conn.execute('''
                SELECT market_category,
                       COUNT(*) as total,
                       SUM(CASE WHEN action = 'BUY' AND t.actual_pnl > 0 THEN 1
                                WHEN action = 'SELL' AND t.actual_pnl < 0 THEN 1
                                ELSE 0 END) as correct
                FROM signal_log s
                LEFT JOIN trades t ON s.market_id = t.market_id 
                    AND t.date >= ? AND s.timestamp <= t.timestamp
                WHERE s.timestamp >= ?
                GROUP BY market_category
                HAVING total >= 3
            ''', (since, since))
            
            return {
                row['market_category']: row['correct'] / row['total'] 
                for row in cursor.fetchall() 
                if row['total'] >= 3 and row['correct'] is not None
            }
