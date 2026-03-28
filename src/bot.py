# Luna Trading Bot - Polymarket Auto Trader
# Conservative & Self-Evolving Strategy
# Phase 1-4 Compounding Focus

import os
import sys
import time
import json
import sqlite3
import logging
import schedule
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Mock mode - CLOB client not loaded
CLOB_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - 🌙 LUNA - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/app/logs/luna_bot.log')
    ]
)
logger = logging.getLogger(__name__)

class LunaTradingBot:
    """
    Luna - Conservative Polymarket Trading Bot
    Self-evolving with phase-based strategy
    """
    
    # Phase configuration
    PHASES = {
        1: {'max_position': 0.05, 'min_confidence': 0.80, 'name': 'Safety First'},
        2: {'max_position': 0.10, 'min_confidence': 0.75, 'name': 'Steady Growth'},
        3: {'max_position': 0.15, 'min_confidence': 0.70, 'name': 'Confident Expansion'},
        4: {'max_position': 0.25, 'min_confidence': 0.65, 'name': 'Aggressive Compounding'}
    }
    
    def __init__(self):
        load_dotenv()
        
        # Capital & Phase
        self.initial_capital = float(os.getenv('INITIAL_CAPITAL', 5.0))
        self.current_capital = self.initial_capital
        self.phase = int(os.getenv('START_PHASE', 1))
        
        # Risk management
        self.max_daily_loss = float(os.getenv('MAX_DAILY_LOSS', 0.20))  # 20% drawdown
        self.daily_pnl = 0.0
        self.last_reset = datetime.now().date()
        
        # Trading config
        self.check_interval = int(os.getenv('CHECK_INTERVAL_MINUTES', 5))
        self.min_liquidity = float(os.getenv('MIN_LIQUIDITY', 10000))  # $10k min
        
        # Initialize
        self.init_database()
        self.load_memory()
        
        logger.info(f"🌙 Luna Bot Initialized")
        logger.info(f"💰 Capital: ${self.current_capital:.2f} | Phase: {self.phase} ({self.PHASES[self.phase]['name']})")
        logger.info(f"🎯 Max Position: {self.PHASES[self.phase]['max_position']*100:.0f}% | Min Confidence: {self.PHASES[self.phase]['min_confidence']*100:.0f}%")

    def init_database(self):
        """Initialize SQLite for trade memory and evolution"""
        try:
            conn = sqlite3.connect('/app/data/luna_memory.db')
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
            
            # Daily evolution table
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
            
            # Market analysis memory
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS market_memory (
                    market_id TEXT PRIMARY KEY,
                    first_seen TEXT,
                    last_analyzed TEXT,
                    total_signals INTEGER,
                    successful_signals INTEGER,
                    avg_confidence REAL,
                    market_category TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("✅ Database initialized")
        except Exception as e:
            logger.error(f"❌ Database init failed: {e}")
            raise

    def load_memory(self):
        """Load previous session data"""
        try:
            conn = sqlite3.connect('/app/data/luna_memory.db')
            cursor = conn.cursor()
            
            # Get latest capital
            cursor.execute('''
                SELECT ending_capital FROM evolution 
                ORDER BY date DESC LIMIT 1
            ''')
            result = cursor.fetchone()
            if result and result[0]:
                self.current_capital = result[0]
                logger.info(f"📊 Loaded capital from memory: ${self.current_capital:.2f}")
            
            # Check phase progression
            cursor.execute('''
                SELECT COUNT(*) FROM trades WHERE status = 'CLOSED' AND actual_pnl > 0
            ''')
            wins = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT COUNT(*) FROM trades WHERE status = 'CLOSED'
            ''')
            total = cursor.fetchone()[0]
            
            if total > 0:
                win_rate = wins / total
                logger.info(f"📈 Historical Win Rate: {win_rate*100:.1f}% ({wins}/{total})")
                
                # Auto phase progression logic
                if win_rate > 0.70 and self.phase < 4 and total >= 10:
                    logger.info(f"🚀 Win rate >70% with {total} trades - ready for Phase {self.phase + 1}")
            
            conn.close()
        except Exception as e:
            logger.warning(f"⚠️ Could not load memory: {e}")

    def calculate_position_size(self, confidence, price=0.5):
        """
        Calculate position size based on phase and confidence
        Returns: size in USD
        """
        phase_config = self.PHASES[self.phase]
        base_size = self.current_capital * phase_config['max_position']
        
        # Adjust by confidence (higher confidence = larger position)
        confidence_multiplier = min(confidence / phase_config['min_confidence'], 1.5)
        
        # Adjust by price (closer to 0.5 = more uncertain, smaller position)
        price_uncertainty = 1 - abs(price - 0.5) * 2  # 0.5 -> 0, 0/1 -> 1
        price_adjustment = 0.5 + (price_uncertainty * 0.5)  # 0.5 to 1.0
        
        final_size = base_size * confidence_multiplier * price_adjustment
        
        # Hard limits
        max_single_trade = self.current_capital * 0.25  # Never more than 25%
        final_size = min(final_size, max_single_trade)
        
        return round(final_size, 2)

    def check_drawdown(self):
        """Check if daily drawdown exceeded"""
        today = datetime.now().date()
        
        # Reset daily PnL if new day
        if today != self.last_reset:
            self.daily_pnl = 0.0
            self.last_reset = today
            logger.info("📅 New day - daily PnL reset")
        
        drawdown_pct = abs(self.daily_pnl) / self.current_capital if self.current_capital > 0 else 0
        
        if drawdown_pct >= self.max_daily_loss:
            logger.warning(f"🛑 Daily drawdown limit hit: {drawdown_pct*100:.1f}%")
            return False
        
        return True

    def analyze_market(self, market_data):
        """
        Luna's market analysis logic
        Returns: (action, confidence, reason)
        """
        # Placeholder - will be implemented with actual Polymarket data
        # This is where Luna's AI/strategy goes
        
        # Example conservative criteria:
        # - High liquidity (> $10k)
        # - Clear directional signal
        # - Price not too extreme (< 0.85 or > 0.15)
        # - Recent volume spike
        
        return 'HOLD', 0.0, 'Analysis placeholder - waiting for market data'

    def log_trade(self, market_id, market_name, action, side, size, price, confidence, expected_return):
        """Log trade to database"""
        try:
            conn = sqlite3.connect('/app/data/luna_memory.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO trades 
                (date, market_id, market_name, action, side, size, price, confidence, expected_return, phase)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                market_id,
                market_name,
                action,
                side,
                size,
                price,
                confidence,
                expected_return,
                self.phase
            ))
            
            conn.commit()
            conn.close()
            logger.info(f"📝 Trade logged: {action} {side} ${size} @ {price}")
        except Exception as e:
            logger.error(f"❌ Failed to log trade: {e}")

    def generate_daily_report(self):
        """Generate daily evolution report"""
        try:
            conn = sqlite3.connect('/app/data/luna_memory.db')
            cursor = conn.cursor()
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Get today's stats
            cursor.execute('''
                SELECT COUNT(*), 
                       SUM(CASE WHEN actual_pnl > 0 THEN 1 ELSE 0 END),
                       SUM(actual_pnl)
                FROM trades 
                WHERE date = ? AND status = 'CLOSED'
            ''', (today,))
            
            total, wins, pnl = cursor.fetchone()
            wins = wins or 0
            pnl = pnl or 0
            
            win_rate = (wins / total * 100) if total > 0 else 0
            roi = (pnl / self.current_capital * 100) if self.current_capital > 0 else 0
            
            # Save to evolution
            cursor.execute('''
                INSERT OR REPLACE INTO evolution 
                (date, starting_capital, ending_capital, total_trades, winning_trades, 
                 losing_trades, win_rate, roi_percent, phase)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                today,
                self.current_capital - pnl,
                self.current_capital,
                total or 0,
                wins,
                (total or 0) - wins,
                win_rate,
                roi,
                self.phase
            ))
            
            conn.commit()
            conn.close()
            
            report = f"""
📊 LUNA DAILY REPORT - {today}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 Capital: ${self.current_capital:.2f} (PnL: ${pnl:+.2f}, ROI: {roi:+.2f}%)
📈 Trades: {total or 0} | ✅ Wins: {wins} | ❌ Losses: {(total or 0) - wins}
🎯 Win Rate: {win_rate:.1f}%
🚀 Phase: {self.phase} ({self.PHASES[self.phase]['name']})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            """
            
            logger.info(report)
            return report
            
        except Exception as e:
            logger.error(f"❌ Daily report failed: {e}")
            return None

    def check_markets(self):
        """Main market checking loop"""
        logger.info("🔍 Checking markets...")
        
        # Check drawdown limit
        if not self.check_drawdown():
            logger.warning("⏸️ Trading paused due to drawdown limit")
            return
        
        # Placeholder: In real implementation, fetch from Polymarket CLOB
        # markets = self.client.get_markets()
        
        logger.info("ℹ️ Market check complete (waiting for Polymarket connection)")

    def run(self):
        """Main bot loop"""
        logger.info("🚀 Luna Bot Starting...")
        logger.info(f"⏱️ Check interval: {self.check_interval} minutes")
        
        # Schedule tasks
        schedule.every(self.check_interval).minutes.do(self.check_markets)
        schedule.every().day.at("23:55").do(self.generate_daily_report)
        
        # Initial check
        self.check_markets()
        
        # Main loop
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except KeyboardInterrupt:
                logger.info("👋 Luna Bot shutting down gracefully...")
                self.generate_daily_report()
                break
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}")
                time.sleep(60)

if __name__ == "__main__":
    bot = LunaTradingBot()
    bot.run()
