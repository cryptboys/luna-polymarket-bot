# Database & Memory Management for Luna Bot

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class LunaMemory:
    """
    Persistent memory for Luna Bot
    Stores: trades, evolution, market history
    """
    
    def __init__(self, db_path: str = '/app/data/luna_memory.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize all tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Trades table
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
                expected_return REAL,
                actual_pnl REAL,
                status TEXT DEFAULT 'OPEN',
                exit_price REAL,
                exit_time TEXT,
                lesson_learned TEXT,
                phase INTEGER
            )
        ''')
        
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
        
        # Market memory
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS market_memory (
                market_id TEXT PRIMARY KEY,
                first_seen TEXT,
                last_analyzed TEXT,
                total_signals INTEGER DEFAULT 0,
                successful_signals INTEGER DEFAULT 0,
                avg_confidence REAL,
                market_category TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")
    
    def log_trade(self, trade_data: Dict[str, Any]) -> int:
        """Log a new trade"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO trades 
            (date, market_id, market_name, action, side, size, price, 
             confidence, expected_return, phase)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().strftime('%Y-%m-%d'),
            trade_data.get('market_id'),
            trade_data.get('market_name'),
            trade_data.get('action'),
            trade_data.get('side'),
            trade_data.get('size'),
            trade_data.get('price'),
            trade_data.get('confidence'),
            trade_data.get('expected_return'),
            trade_data.get('phase', 1)
        ))
        
        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return trade_id
    
    def close_trade(self, trade_id: int, exit_price: float, pnl: float, lesson: str = ''):
        """Close a trade and record PnL"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE trades 
            SET status = 'CLOSED',
                exit_price = ?,
                exit_time = ?,
                actual_pnl = ?,
                lesson_learned = ?
            WHERE id = ?
        ''', (exit_price, datetime.now().isoformat(), pnl, lesson, trade_id))
        
        conn.commit()
        conn.close()
    
    def get_open_trades(self) -> List[Dict]:
        """Get all open trades"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trades WHERE status = 'OPEN'
            ORDER BY timestamp DESC
        ''')
        
        trades = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return trades
    
    def get_trade_history(self, days: int = 30) -> List[Dict]:
        """Get trade history for analysis"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        cursor.execute('''
            SELECT * FROM trades 
            WHERE date >= ?
            ORDER BY timestamp DESC
        ''', (since,))
        
        trades = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return trades
    
    def get_performance_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get performance statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # Overall stats
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN actual_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN actual_pnl < 0 THEN 1 ELSE 0 END) as losses,
                SUM(actual_pnl) as total_pnl,
                AVG(actual_pnl) as avg_pnl
            FROM trades 
            WHERE date >= ? AND status = 'CLOSED'
        ''', (since,))
        
        row = cursor.fetchone()
        total, wins, losses, total_pnl, avg_pnl = row
        
        win_rate = (wins / total * 100) if total > 0 else 0
        
        # By phase
        cursor.execute('''
            SELECT phase, 
                   COUNT(*) as count,
                   SUM(CASE WHEN actual_pnl > 0 THEN 1 ELSE 0 END) as phase_wins
            FROM trades 
            WHERE date >= ? AND status = 'CLOSED'
            GROUP BY phase
        ''', (since,))
        
        phase_stats = {row[0]: {'total': row[1], 'wins': row[2]} 
                      for row in cursor.fetchall()}
        
        conn.close()
        
        return {
            'period_days': days,
            'total_trades': total or 0,
            'wins': wins or 0,
            'losses': losses or 0,
            'win_rate': win_rate,
            'total_pnl': total_pnl or 0,
            'avg_pnl': avg_pnl or 0,
            'by_phase': phase_stats
        }
    
    def save_evolution(self, date: str, data: Dict[str, Any]):
        """Save daily evolution data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO evolution 
            (date, starting_capital, ending_capital, total_trades, 
             winning_trades, losing_trades, win_rate, roi_percent, 
             lessons, phase)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            date,
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
        conn.close()
    
    def get_lessons_learned(self, limit: int = 10) -> List[str]:
        """Extract lessons from past trades"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT lesson_learned FROM trades 
            WHERE lesson_learned IS NOT NULL 
              AND lesson_learned != ''
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        lessons = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return lessons
    
    def update_market_memory(self, market_id: str, category: str, signal_success: bool):
        """Update market-specific memory"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO market_memory (market_id, first_seen, last_analyzed, 
                                       total_signals, successful_signals, market_category)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(market_id) DO UPDATE SET
                last_analyzed = ?,
                total_signals = total_signals + 1,
                successful_signals = successful_signals + ?
        ''', (
            market_id,
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            1 if signal_success else 0,
            category,
            datetime.now().isoformat(),
            1 if signal_success else 0
        ))
        
        conn.commit()
        conn.close()
    
    def get_market_memory(self, market_id: str) -> Optional[Dict]:
        """Get memory for specific market"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM market_memory WHERE market_id = ?
        ''', (market_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            data = dict(row)
            # Calculate win rate
            if data['total_signals'] > 0:
                data['win_rate'] = data['successful_signals'] / data['total_signals']
            else:
                data['win_rate'] = 0
            return data
        
        return None
