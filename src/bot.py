#!/usr/bin/env python3
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
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Ensure paths exist (both local dev AND Railway docker)
def _ensure_dirs():
    """Create data/logs directories relative to project root"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base, 'data')
    logs_dir = os.path.join(base, 'logs')
    for d in [data_dir, logs_dir]:
        os.makedirs(d, exist_ok=True)
    return data_dir, logs_dir

DATA_DIR, LOGS_DIR = _ensure_dirs()

# Try to import PolymarketClient
try:
    from src.polymarket import PolymarketClient, OrderManager
    from src.strategy import LunaStrategy
    from src.database import LunaMemory
    MODULES_LOADED = True
except ImportError as e:
    MODULES_LOADED = False
    print(f"⚠️  Modules not available: {e}")

# Setup logging
log_file = os.path.join(LOGS_DIR, 'luna_bot.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - 🌙 LUNA - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding='utf-8')
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
        
        # Paper trading mode
        self.paper_trading = os.getenv('PAPER_TRADING', 'true').lower() == 'true'
        self.virtual_balance = self.initial_capital if self.paper_trading else 0
        
        # Initialize CLOB client if available
        self.clob_client = None
        self.order_manager = None
        self.polymarket = None
        self.strategy = None
        self.memory = None
        
        # Database
        self.db_path = os.path.join(DATA_DIR, 'luna_memory.db')
        
        # Health check endpoint (for Railway)
        self._health_ok = False
        
        # Initialize
        self._init_components()
        
        logger.info(f"🌙 Luna Bot Initialized")
        logger.info(f"💰 Capital: ${self.current_capital:.2f} | Phase: {self.phase} ({self.PHASES[self.phase]['name']})")
        logger.info(f"🎯 Max Position: {self.PHASES[self.phase]['max_position']*100:.0f}% | Min Confidence: {self.PHASES[self.phase]['min_confidence']*100:.0f}%")
        
        if self.paper_trading:
            logger.info("📊 PAPER TRADING MODE - No real money at risk")
            logger.info(f"💵 Virtual Balance: ${self.virtual_balance:.2f}")
        elif self.clob_client:
            logger.info("✅ Connected to Polymarket CLOB - LIVE TRADING")
        else:
            logger.info("⚠️ Running in mock mode (no CLOB connection)")

    def _init_components(self):
        """Initialize all bot components"""
        try:
            # Memory (always — paper or live)
            self.memory = LunaMemory(db_path=self.db_path)
            self.memory.load_capital_into(self)
            
            # Strategy
            self.strategy = LunaStrategy(phase=self.phase)
            
            # Polymarket client
            if not self.paper_trading:
                private_key = os.getenv('POLY_PRIVATE_KEY')
                if private_key:
                    self.polymarket = PolymarketClient(
                        api_key=os.getenv('POLY_API_KEY'),
                        api_secret=os.getenv('POLY_API_SECRET'),
                        passphrase=os.getenv('POLY_PASSPHRASE'),
                        private_key=private_key,
                    )
                    self.order_manager = OrderManager(self.polymarket)
                    if self.polymarket.is_connected():
                        logger.info("✅ Polymarket CLOB client connected")
                        balance = self.polymarket.get_balance()
                        if balance > 0:
                            logger.info(f"💵 CLOB Balance: ${balance:.2f}")
                    else:
                        logger.warning("⚠️ Polymarket client not connected — check private key & API creds")
                else:
                    logger.warning("⚠️ POLY_PRIVATE_KEY not set — mock mode")
            else:
                logger.info("📊 Paper trading — using mock Polymarket client")
                # Create mock client for paper trading
                self.polymarket = PolymarketClient()
                self.order_manager = OrderManager(self.polymarket)
            
            self._health_ok = True
            
        except Exception as e:
            logger.error(f"❌ Component init failed: {e}")
            self._health_ok = False

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
        price_uncertainty = 1 - abs(float(price) - 0.5) * 2
        price_adjustment = 0.5 + (price_uncertainty * 0.5)
        
        final_size = base_size * confidence_multiplier * price_adjustment
        
        # Hard limits
        max_single_trade = self.current_capital * 0.25
        min_trade = 1.0  # Min $1
        
        final_size = max(min_trade, min(final_size, max_single_trade))
        
        return round(final_size, 2)

    def check_drawdown(self):
        """Check if daily drawdown exceeded"""
        today = datetime.now().date()
        
        if today != self.last_reset:
            self.daily_pnl = 0.0
            self.last_reset = today
            logger.info("📅 New day - daily PnL reset")
        
        drawdown_pct = abs(self.daily_pnl) / self.current_capital if self.current_capital > 0 else 0
        
        if drawdown_pct >= self.max_daily_loss:
            logger.warning(f"🛑 Daily drawdown limit hit: {drawdown_pct*100:.1f}%")
            return False
        
        return True

    def check_markets(self):
        """Main market checking loop"""
        logger.info("🔍 Checking markets...")
        
        if not self.check_drawdown():
            logger.warning("⏸️ Trading paused due to drawdown limit")
            return
        
        if not self.polymarket:
            logger.error("❌ Polymarket client not initialized")
            return
        
        # Fetch markets
        try:
            markets = self.polymarket.get_markets(limit=50)
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return
        
        if not markets:
            logger.info("No markets found — skipping")
            return
        
        logger.info(f"📊 Analyzing {len(markets)} markets...")
        
        # Analyze each market
        for market in markets:
            try:
                # Prepare market data for strategy
                market_data = {
                    'id': market.id,
                    'name': market.name,
                    'category': market.category,
                    'best_bid': market.best_bid,
                    'best_ask': market.best_ask,
                    'liquidity': market.liquidity,
                    'volume_24h': market.volume_24h,
                    'price_change_24h': market.price_change_24h,
                    'days_to_resolution': market.days_to_resolution,
                    'slug': market.slug,
                }
                
                # Strategy analysis
                if self.strategy:
                    action, confidence, reason = self.strategy.analyze_market(
                        market_data, 
                        memory=self.memory.get_market_memory(market.id) if self.memory else None
                    )
                    
                    if action in ('BUY', 'SELL'):
                        # Calculate position size
                        mid_price = (market.best_bid + market.best_ask) / 2
                        size = self.calculate_position_size(confidence, mid_price)
                        
                        logger.info(f"🎯 SIGNAL: {action} — {market.name[:60]}")
                        logger.info(f"   Confidence: {confidence:.1%} | Size: ${size:.2f}")
                        logger.info(f"   Reason: {reason}")
                        
                        if size >= 1.0:  # Only trade if size >= $1
                            if self.paper_trading:
                                # Paper trade
                                self._execute_paper_trade(market, action, size, confidence, reason, mid_price)
                            elif self.order_manager:
                                # Live trade
                                self._execute_live_trade(market, action, size, confidence, reason, mid_price)
                            else:
                                logger.warning("⚠️ No order manager — cannot execute trade")
                
            except Exception as e:
                logger.warning(f"Error analyzing market {market.id}: {e}")
                continue
            
            # Sleep between markets to avoid rate limiting
            time.sleep(0.5)
        
        logger.info(f"✅ Market check complete — analyzed {len(markets)} markets")

    def _execute_paper_trade(self, market, action, size, confidence, reason, price):
        """Execute a simulated trade in paper mode"""
        side = 'Yes' if action == 'BUY' else 'No'
        
        # Simulate trade
        cost = size * (1 - price) if action == 'SELL' else size * price
        potential_return = size - cost
        expected_roi = (potential_return / cost * 100) if cost > 0 else 0
        
        logger.info(f"📝 PAPER TRADE: {action} ${size:.2f} {side} @ ${price:.3f}")
        logger.info(f"   Cost: ${cost:.2f} | Potential return: ${potential_return:.2f} ({expected_roi:.1f}%)")
        
        # Log to database
        if self.memory:
            self.memory.log_paper_trade({
                'market_id': market.id,
                'market_name': market.name,
                'action': action,
                'side': side,
                'size': size,
                'price': price,
                'confidence': confidence,
                'cost': cost,
                'potential_return': potential_return,
                'expected_roi': expected_roi,
                'reason': reason,
                'phase': self.phase,
            })
        
        # Adjust virtual balance
        self.virtual_balance -= cost
        logger.info(f"💵 Virtual balance: ${self.virtual_balance:.2f}")
        
        # Phase progression check
        self._check_phase_progression()
    
    def _execute_live_trade(self, market, action, confidence, reason, price):
        """Execute a real trade via CLOB"""
        side = action  # BUY or SELL
        
        result = self.order_manager.submit_order(
            market_id=market.id,
            side=side,
            size=0.0,  # Size determined by strategy
            confidence=confidence,
        )
        
        if result.get('success'):
            logger.info(f"✅ LIVE TRADE: {result}")
            if self.memory:
                self.memory.log_live_trade({
                    'market_id': market.id,
                    'market_name': market.name,
                    'action': action,
                    'size': result.get('size', 0),
                    'price': result.get('price', price),
                    'confidence': confidence,
                    'order_id': result.get('order_id', ''),
                    'phase': self.phase,
                })
        else:
            logger.error(f"❌ Trade failed: {result.get('error', 'Unknown error')}")

    def _check_phase_progression(self):
        """Check if bot should advance to next phase"""
        if self.memory:
            stats = self.memory.get_trading_stats()
            closed_trades = stats.get('total_closed', 0)
            win_rate = stats.get('win_rate', 0)
            
            if closed_trades >= 10 and win_rate > 0.70 and self.phase < 4:
                logger.info(f"🚀 Win rate {win_rate:.1%} with {closed_trades} trades — ready for Phase {self.phase + 1}!")
                self.phase += 1
                logger.info(f"📈 Phase advanced to {self.phase} ({self.PHASES[self.phase]['name']})")
                
                if self.strategy:
                    self.strategy.phase = self.phase

    def generate_daily_report(self):
        """Generate daily evolution report"""
        try:
            if not self.memory:
                logger.warning("No memory module — cannot generate report")
                return None
            
            today = datetime.now().strftime('%Y-%m-%d')
            stats = self.memory.get_trading_stats(today)
            
            total_trades = stats.get('total_trades', 0)
            wins = stats.get('winning_trades', 0)
            losses = stats.get('losing_trades', 0)
            win_rate = stats.get('win_rate', 0)
            pnl = stats.get('pnl', 0)
            roi = stats.get('roi', 0)
            
            # Save evolution
            self.memory.save_daily_evolution({
                'date': today,
                'starting_capital': self.current_capital,
                'ending_capital': self.current_capital + pnl,
                'total_trades': total_trades,
                'winning_trades': wins,
                'losing_trades': losses,
                'win_rate': win_rate,
                'roi_percent': roi,
                'phase': self.phase,
            })
            
            report = f"""📊 LUNA DAILY REPORT - {today}

💰 Capital: ${self.current_capital:.2f}
📈 PnL: ${pnl:+.2f} ({roi:+.2f}%)
🎯 Trades: {total_trades} | ✅ Wins: {wins} | ❌ Losses: {losses}
🏆 Win Rate: {win_rate:.1%}
🚀 Phase: {self.phase} ({self.PHASES[self.phase]['name']})
💵 Virtual Balance: ${self.virtual_balance:.2f}

Keep compounding! 🌙"""
            
            logger.info(report)
            
            # Send Telegram alert if configured
            self._send_telegram_alert(report)
            
            return report
            
        except Exception as e:
            logger.error(f"❌ Daily report failed: {e}")
            return None

    def _send_telegram_alert(self, message: str):
        """Send alert via Telegram"""
        try:
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            chat_id = os.getenv('TELEGRAM_CHAT_ID')
            
            if not bot_token or not chat_id:
                return
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
            }
            
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("📱 Telegram alert sent")
            else:
                logger.warning(f"⚠️ Telegram API error: {resp.status_code}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to send Telegram alert: {e}")

    def run(self):
        """Main bot loop"""
        logger.info("🚀 Luna Bot Starting...")
        logger.info(f"⏱️ Check interval: {self.check_interval} minutes")
        logger.info(f"📊 Mode: {'PAPER' if self.paper_trading else 'LIVE'}")
        logger.info(f"🛡️ Max daily drawdown: {self.max_daily_loss*100:.0f}%")
        
        # Schedule tasks
        schedule.every(self.check_interval).minutes.do(self.check_markets)
        schedule.every().day.at("23:55").do(self.generate_daily_report)
        
        # Initial check
        self.check_markets()
        
        # Main loop
        while True:
            try:
                schedule.run_pending()
                time.sleep(30)  # Check every 30 seconds for graceful shutdown
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
