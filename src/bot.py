#!/usr/bin/env python3
# Luna Trading Bot - Polymarket Auto Trader
# Phase 3: Portfolio Management, Auto-Close, Dynamic Phase, Health Monitoring

import os
import sys
import time
import json
import logging
import schedule
import requests
import traceback
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

# Import modules
try:
    from src.polymarket import PolymarketClient, OrderManager, Market
    from src.strategy import LunaStrategy, RiskManager, EVResult
    from src.database import LunaMemory
    from src.portfolio import PortfolioManager, PositionState
    from src.orderbook import OrderBookAnalyzer, OrderBookTracker
    from src.correlation import CorrelationEngine
    from src.news import NewsAnalyzer
    from src.evolution import EvolutionEngine
    from src.compounding import CompoundingEngine
    from src.market_filter import MarketFilter, MarketFilterConfig
    from src.price_service import PriceService, GammaPriceProvider, PaperPriceProvider
    from src.kelly_cache import KellyCache
    from src.pnl import PnlCalculator
    from src.rate_limiter import ApiRateLimiter
    from src.llm_router import LlmRouter, llm_analyze
    from src.backtest import Backtester
    from src.dashboard import start_dashboard
    MODULES_LOADED = True
except ImportError as e:
    MODULES_LOADED = False
    print(f"⚠️  Modules not available: {e}\n{traceback.format_exc()}")

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
    Phase 3: Portfolio management, auto-close, dynamic phase, health monitoring
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
        self.max_daily_loss_pct = float(os.getenv('MAX_DAILY_LOSS', 0.20))
        self.daily_pnl = 0.0
        self.last_reset = datetime.now().date()
        
        # Trading config
        self.check_interval = int(os.getenv('CHECK_INTERVAL_MINUTES', 5))
        self.min_liquidity = float(os.getenv('MIN_LIQUIDITY', 10000))
        
        # Paper trading mode
        self.paper_trading = os.getenv('PAPER_TRADING', 'true').lower() == 'true'
        self.virtual_balance = self.initial_capital if self.paper_trading else 0
        
        # Phase 3 components
        self.polymarket = None
        self.order_manager = None
        self.strategy = None
        self.memory = None
        self.portfolio = None
        self.risk_manager = None
        
        # Phase 4 components
        self.orderbook_analyzer = None
        self.orderbook_tracker = None
        self.correlation_engine = None
        self.dashboard_server = None
        self.enable_orderbook = os.getenv('ENABLE_ORDERBOOK', 'true').lower() == 'true'
        self.enable_correlation = os.getenv('ENABLE_CORRELATION', 'true').lower() == 'true'
        self.enable_news = os.getenv('ENABLE_NEWS', 'true').lower() == 'true'
        self.enable_evolution = os.getenv('ENABLE_EVOLUTION', 'true').lower() == 'true'
        self.enable_dashboard = os.getenv('ENABLE_DASHBOARD', 'true').lower() == 'true'
        self.enable_compounding = os.getenv('ENABLE_COMPOUNDING', 'true').lower() == 'true'
        self.enable_llm = os.getenv('ENABLE_LLM', 'true').lower() == 'true'
        self.enable_market_filter = os.getenv('ENABLE_MARKET_FILTER', 'true').lower() == 'true'
        self.dashboard_port = int(os.getenv('DASHBOARD_PORT', 8080))
        
        # State
        self._health_ok = False
        self._running = False
        self._errors_last_hour = 0
        self._last_error_time = 0
        
        # Database path
        self.db_path = os.path.join(DATA_DIR, 'luna_memory.db')
        
        # Initialize everything
        self._init_all()
        
        logger.info(f"🌙 Luna Bot Phase 6 Initialized")
        logger.info(f"💰 Capital: ${self.current_capital:.2f} | Phase: {self.phase} ({self.PHASES[self.phase]['name']})")
        logger.info(f"📊 Mode: {'📝 PAPER TRADING' if self.paper_trading else '🔴 LIVE TRADING'}")
        logger.info(f"⏱️ Check interval: {self.check_interval}m | Max daily loss: {self.max_daily_loss_pct*100:.0f}%")

    def _init_all(self):
        """Initialize all components with error recovery"""
        try:
            # 1. Memory (always)
            self.memory = LunaMemory(db_path=self.db_path)
            self.memory.load_capital_into(self)
            logger.info(f"✅ Memory loaded: ${self.current_capital:.2f}")
            
            # 2. Strategy
            self.strategy = LunaStrategy(phase=self.phase)
            self.risk_manager = RiskManager(capital=self.current_capital, phase=self.phase)
            logger.info(f"✅ Strategy Phase {self.phase}: {self.PHASES[self.phase]['name']}")
            
            # 3. Portfolio Manager
            self.portfolio = PortfolioManager(
                capital=self.current_capital,
                phase=self.phase,
                db_memory=self.memory
            )
            logger.info(f"✅ Portfolio manager ready")
            
            # 4. Polymarket client
            if not self.paper_trading:
                private_key = os.getenv('POLY_PRIVATE_KEY')
                if private_key:
                    try:
                        self.polymarket = PolymarketClient(
                            api_key=os.getenv('POLY_API_KEY'),
                            api_secret=os.getenv('POLY_API_SECRET'),
                            passphrase=os.getenv('POLY_PASSPHRASE'),
                            private_key=private_key,
                        )
                        self.order_manager = OrderManager(self.polymarket)
                        if self.polymarket.is_connected():
                            balance = self.polymarket.get_balance()
                            logger.info(f"✅ CLOB connected | Balance: ${balance:.2f}")
                        else:
                            logger.warning("⚠️ CLOB not fully connected — check API creds")
                    except Exception as e:
                        logger.error(f"❌ CLOB init failed: {e}")
                else:
                    logger.warning("⚠️ POLY_PRIVATE_KEY not set — mock mode for paper")
            
            # Paper trading: use mock client
            if self.paper_trading or not self.polymarket:
                self.polymarket = PolymarketClient()
                self.order_manager = OrderManager(self.polymarket)
                logger.info("📝 Using mock Polymarket client for paper trading")
            
            # Sync portfolio capital from bot
            self.portfolio.capital = self.current_capital
            
            # Phase 4: Order Book Analyzer
            if self.enable_orderbook:
                self.orderbook_analyzer = OrderBookAnalyzer(self.polymarket)
                self.orderbook_tracker = OrderBookTracker(self.orderbook_analyzer)
                logger.info("📊 Order book intelligence enabled")
            
            # Phase 5.2: Correlation Engine
            if self.enable_correlation:
                self.correlation_engine = CorrelationEngine()
                logger.info("🔗 Correlation engine enabled")
            
            # Phase 5.2: News Sentiment
            if self.enable_news:
                self.news_analyzer = NewsAnalyzer()
                logger.info("📰 News Sentiment analyzer enabled")
            
            # Phase 3: Online Learning (Evolution)
            self.evolution_engine = None
            if self.enable_evolution:
                self.evolution_engine = EvolutionEngine(db_path=self.db_path, strategy_instance=self.strategy)
                logger.info("🧠 Evolution Engine enabled (Auto-tuning weights)")
                # Push any existing evolved weights to strategy immediately
                self.evolution_engine._apply_to_strategy()
            
            # Phase 6: Compounding Protocol
            self.compounding = None
            if self.enable_compounding:
                self.compounding = CompoundingEngine(
                    fractional_constant=float(os.getenv('KELLY_FRACTION', 0.25)),
                    max_position_pct=self.PHASES[self.phase]['max_position'],
                    min_profit_offload=float(os.getenv('MIN_PROFIT_OFFLOAD', 0.10))
                )
                logger.info(f"📈 Compounding Protocol enabled (Quarter Kelly, {self.PHASES[self.phase]['max_position']*100:.0f}% max)")

            # Efficiency: Market Filter
            self.market_filter = None
            if self.enable_market_filter:
                self.market_filter = MarketFilter(MarketFilterConfig(
                    max_duration_hours=int(os.getenv('MAX_DURATION_HOURS', 168)),
                    min_liquidity=self.min_liquidity,
                    min_volume_24h=float(os.getenv('MIN_VOLUME_24H', 1000)),
                    max_spread_bps=int(os.getenv('MAX_SPREAD_BPS', 200)),
                ))
                logger.info(f"🚧 Market Filter enabled (max {int(os.getenv('MAX_DURATION_HOURS', 168))}h duration)")

            # Efficiency: Price Service
            self.price_service = None
            if self.enable_market_filter or self.compounding:
                gamma = GammaPriceProvider()
                paper = PaperPriceProvider()
                self.price_service = PriceService(
                    gamma_provider=gamma,
                    paper_provider=paper,
                    use_paper=self.paper_trading
                )

            # Efficiency: Kelly Cache
            self.kelly_cache = KellyCache()

            # Efficiency: Rate Limiter
            self.rate_limiter = ApiRateLimiter()

            # LLM: Multi-model router (free models primary, qwen3.5-flash fallback)
            self.enable_llm = os.getenv('ENABLE_LLM', 'true').lower() == 'true'
            self.llm_router = None
            if self.enable_llm:
                try:
                    self.llm_router = LlmRouter()
                    logger.info("🧠 LLM Router: 4 free models + qwen3.5-flash fallback")
                except Exception as e:
                    logger.warning(f"LLM Router init failed: {e}")

            # Phase 4: Dashboard
            if self.enable_dashboard:
                import threading
                self.dashboard_server = start_dashboard(self, self.dashboard_port)
                if self.dashboard_server:
                    threading.Thread(target=self.dashboard_server.serve_forever, daemon=True).start()
                    logger.info(f"🌐 Dashboard running on port {self.dashboard_port}")
            
            self._health_ok = True
            self._errors_last_hour = 0
            
        except Exception as e:
            logger.error(f"❌ Init failed: {e}\n{traceback.format_exc()}")
            self._health_ok = False

    # ═══════════════════════════════════════════
    # MAIN WORKFLOW
    # ═══════════════════════════════════════════
    
    def check_markets(self):
        """Main market checking loop — Phase 3"""
        logger.info("🔍 Checking markets...")
        
        try:
            # 1. Health check
            health = self._run_health_check()
            if health['status'] == 'critical':
                logger.warning(f"⚠️ Health CRITICAL — trading paused. Issues: {health.get('issues', [])}")
                return
            
            if health['status'] == 'warning':
                logger.warning(f"⚠️ Health WARNING: {health.get('issues', [])}")
            
            # 2. Drawdown check
            if not self._check_drawdown():
                logger.warning("⏸️ Trading paused — daily drawdown limit hit")
                return
            
            # 3. Risk manager check
            can_trade, risk_reason = self.risk_manager.can_trade()
            if not can_trade:
                logger.warning(f"⏸️ Risk manager: {risk_reason}")
                return
            
            # 4. Check portfolio lifecycle (TP/SL/Expiry)
            self._check_portfolio_lifecycle()
            
            # 5. Check rebalancing
            self._check_rebalancing()
            
            # 6. Fetch and analyze markets
            self._analyze_and_trade()
            
            # 7. Log session summary
            self._log_session_summary()
            
            # Reset error counter on success
            self._errors_last_hour = 0
            self._health_ok = True
            
        except Exception as e:
            logger.error(f"❌ Market check failed: {e}")
            self._errors_last_hour += 1
            if self._errors_last_hour >= 5:
                logger.error(f"🚨 {self._errors_last_hour} errors in last hour — circuit breaker")
            self._health_ok = False

    def _analyze_and_trade(self):
        if not self.polymarket:
            logger.error("No Polymarket client available")
            return

        try:
            markets = self.polymarket.get_markets(limit=50)
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return

        if not markets:
            logger.info("No markets found")
            return

        opened_ids = {p.market_id for p in self.portfolio.positions.values()} if self.portfolio else set()

        if self.market_filter:
            filtered = []
            for m in markets:
                if m.id in opened_ids:
                    continue
                hours = m.days_to_resolution * 24
                gate = self.market_filter.gate(
                    hours_to_resolution=hours,
                    liquidity=m.liquidity,
                    volume_24h=m.volume_24h,
                    best_bid=m.best_bid,
                    best_ask=m.best_ask,
                    market_age_days=m.market_age_days,
                )
                if gate.passed:
                    m._duration_score = gate.duration_score
                    filtered.append(m)
            logger.info("🚧 " + self.market_filter.gate_count_summary(len(markets), len(filtered)))
            markets = filtered
        else:
            markets = [m for m in markets if m.id not in opened_ids]

        logger.info(f"📊 Analyzing {len(markets)} markets (post-filter)...")
        trades_executed = 0
        hold_count = 0
        no_edge_count = 0

        self.kelly_cache.clear_cycle()

        for market in markets:
            try:
                
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
                    'volume_trend': market.volume_trend,
                    'market_age_days': market.market_age_days,
                }
                
                memory = None
                if self.memory:
                    memory = self.memory.get_market_memory(market.id)
                
                if not self.strategy:
                    continue
                
                # ═══════════════════════════════════════════
                # EV ANALYSIS (Phase 5.1)
                # ═══════════════════════════════════════════
                ev_result: EVResult = self.strategy.analyze_market(market_data, memory)
                
                # Track in history
                if self.memory:
                    self.memory.log_signal(
                        market_id=market.id,
                        market_name=market.name,
                        category=market.category,
                        action=ev_result.action,
                        confidence=ev_result.p_bot,
                        market_score=ev_result.p_bot,
                        kelly_fraction=self._kelly_or_compute(market.id, ev_result.p_bot, ev_result.p_mkt),
                        recommended_side='YES' if ev_result.p_bot > ev_result.p_mkt else 'NO',
                        phase=self.phase,
                    )
                
                # ═══════════════════════════════════════════
                # ORDER BOOK INTELLIGENCE (optional boost)
                # ═══════════════════════════════════════════
                ev = ev_result.ev
                p_bot = ev_result.p_bot
                p_mkt = ev_result.p_mkt
                side = 'YES' if p_bot > p_mkt else 'NO'
                
                if self.enable_orderbook and self.orderbook_analyzer:
                    try:
                        ob_analysis = self.orderbook_analyzer.analyze(market.id, market.id)
                        if ob_analysis:
                            ob_signals = self.orderbook_analyzer.get_trading_signals(ob_analysis)
                            ob_adj = ob_signals['confidence_adjustment']
                            if ob_signals['recommended_action'] == 'BEARISH':
                                p_bot = max(0.01, p_bot - abs(ob_adj) * 0.5)
                            elif ob_signals['recommended_action'] == 'BULLISH':
                                p_bot = min(0.99, p_bot + abs(ob_adj) * 0.5)
                            
                            if self.orderbook_tracker:
                                self.orderbook_tracker.update(market.id)
                    except Exception as e:
                        logger.debug(f"Order book analysis skipped: {e}")
                
                # Recheck EV after orderbook adjustment
                spread = market.best_ask - market.best_bid
                c_total = p_mkt + (spread * 0.5)
                w_net = 1.0 - c_total
                ev = (p_bot * w_net) - ((1 - p_bot) * c_total)
                
                # ═══════════════════════════════════════════
                # CORRELATION CHECK
                # ═══════════════════════════════════════════
                if self.enable_correlation and self.correlation_engine and ev_result.action == 'BUY':
                    current_pos = self.portfolio.get_open_positions_detail() if self.portfolio else []
                    test_size = self.risk_manager.calculate_size(p_bot, p_mkt)
                    
                    can_open, corr_reason = self.correlation_engine.should_open_position(
                        market.name, market.category, test_size,
                        [{'market_name': p['market'], 'size': p['size'], 'side': p['side'], 'category': market.category} for p in current_pos]
                    )
                    
                    if not can_open:
                        logger.debug(f"Correlation block: {corr_reason}")
                        ev_result = EVResult('HOLD', ev, p_bot, p_mkt, p_bot - p_mkt, f"BLOCKED: {corr_reason}")
                
                # ═══════════════════════════════════════════
                # NEWS SENTIMENT ADJUSTMENT (Phase 5.2)
                # ═══════════════════════════════════════════
                if self.enable_news and ev_result.action == 'BUY':
                    try:
                        news_adj = self.news_analyzer.analyze_market(market.name, market.category)
                        if news_adj != 0:
                            p_bot = max(0.01, min(0.99, p_bot + news_adj))
                            
                            # Recalculate EV
                            c_total = p_mkt + (spread * 0.5)
                            ev = (p_bot * w_net) - ((1 - p_bot) * c_total)
                            
                            logger.info(f"📰 News sentimen: {news_adj:+.4f} -> p_bot {p_bot:.4f}")
                            
                            # Recheck EV gate
                            if p_bot <= p_mkt or ev <= 0:
                                ev_result = EVResult('HOLD', ev, p_bot, p_mkt, p_bot - p_mkt, f"News reversed edge (sentimen: {news_adj:+.4f})")
                    except Exception as e:
                        logger.debug(f"News analysis skipped: {e}")
                
                # ═══════════════════════════════════════════
                # LLM CONTEXT VALIDATION (borderline cases)
                # ═══════════════════════════════════════════
                if ev_result.action == 'BUY' and self.llm_router and 0.01 < ev < 0.05:
                    try:
                        llm_prompt = (
                            f"Market: {market.name}\n"
                            f"Category: {market.category}\n"
                            f"Our probability: {p_bot:.1%}\n"
                            f"Market probability: {p_mkt:.1%}\n"
                            f"Expected Value: ${ev:+.4f}\n"
                            f"Edge: {p_bot - p_mkt:+.1%}\n"
                            f"Liquidity: ${market.liquidity:,.0f}\n"
                            f"Volume 24h: ${market.volume_24h:,.0f}\n\n"
                            f"Question: Is this a legitimate edge or does market structure "
                            f"suggest the edge is artificial? Reply CONCISE (YES/NO + 1 sentence reason)."
                        )
                        llm_result = self.llm_router.call(
                            "You are a prediction market analyst. Evaluate whether a market edge is real or artificial.",
                            llm_prompt,
                            max_tokens=128,
                            temperature=0.2,
                        )
                        if 'NO' in llm_result.upper()[:30]:
                            logger.info(f"🧠 LLM veto: {llm_result}")
                            ev_result = EVResult('HOLD', ev, p_bot, p_mkt, p_bot - p_mkt, f"LLM veto: {llm_result}")
                        else:
                            logger.info(f"🧠 LLM confirm: {llm_result}")
                    except Exception as e:
                        logger.debug(f"LLM validation skipped: {e}")

                # ═══════════════════════════════════════════
                # EXECUTION DECISION
                # ═══════════════════════════════════════════
                if ev_result.action == 'BUY' and ev > 0:
                    # Kelly sizing
                    size = self.risk_manager.calculate_size(p_bot, p_mkt)
                    
                    if size >= 1.0:
                        logger.info(f"🎯 BUY {side} — {market.name[:60]}")
                        logger.info(f"   Our {p_bot:.1%} vs Market {p_mkt:.1%} (edge: {ev_result.edge:+.1%})")
                        kelly = self._kelly_or_compute(market.id, p_bot, p_mkt)
                        logger.info(f"   EV: ${ev:+.4f} | Size: ${size:.2f} | Kelly: {kelly:.1%}")
                        logger.info(f"   Cost: ${c_total:.4f} | WinNet: ${w_net:.4f}")
                        logger.info(f"   Reason: {ev_result.reason}")
                        
                        if self.paper_trading:
                            self._execute_paper_trade(market, side, size, p_bot, p_mkt, ev, market.best_bid)
                            trades_executed += 1
                        elif self.order_manager:
                            self._execute_live_trade(market, side, size, p_bot, p_mkt, ev, market.best_bid)
                            trades_executed += 1
                    else:
                        logger.debug(f"Skip {market.name[:40]}: size ${size:.2f} below $1 min")
                else:
                    hold_count += 1
                    if ev_result.action == 'HOLD' and ev_result.edge <= 0:
                        no_edge_count += 1
                    logger.debug(f"  HOLD {market.name[:40]} | {ev_result.reason}")
                
            except Exception as e:
                logger.debug(f"Error analyzing {market.id}: {e}")
                continue
            
            time.sleep(0.3)
        
        logger.info(f"✅ Scanned {len(markets)} | {trades_executed} trades | {hold_count} holds ({no_edge_count} no-edge)")

    # ═══════════════════════════════════════════
    # TRADE EXECUTION — Phase 5.1: EV-based
    # ═══════════════════════════════════════════
    
    def _execute_paper_trade(self, market, side, size, p_bot, p_mkt, ev, price):
        """Execute simulated trade — EV-based"""
        position_id = f"paper-{market.id}-{datetime.now().strftime('%H%M%S')}"
        
        if side == 'YES':
            cost = size * price
        else:
            cost = size * (1 - price)
        
        max_payout = size
        potential_pnl = max_payout - cost
        expected_roi = (potential_pnl / cost * 100) if cost > 0 else 0
        
        logger.info(f"📝 PAPER: {side} ${size:.2f} @ ${price:.3f} | Cost: ${cost:.2f} | Potential: ${potential_pnl:.2f} ({expected_roi:.0f}%)")
        
        kelly = self._kelly_or_compute(market.id, p_bot, p_mkt)
        self.portfolio.open_position(
            position_id=position_id,
            market_id=market.id,
            market_name=market.name,
            side=side,
            entry_price=price,
            size=size,
            kelly_fraction=kelly,
            market_score=p_bot,
            confidence=p_bot,
        )
        
        if self.price_service:
            self.price_service.record_entry(market.id, price)
        
        self.risk_manager.record_trade(0, size)
        
        if self.memory:
            self.memory.log_paper_trade({
                'market_id': market.id,
                'market_name': market.name,
                'action': 'BUY',
                'side': side,
                'size': size,
                'price': price,
                'confidence': p_bot,
                'market_score': p_bot,
                'kelly_fraction': self._kelly_or_compute(market.id, p_bot, p_mkt),
                'cost': cost,
                'potential_return': potential_pnl,
                'expected_roi': expected_roi,
                'reason': f"P_bot {p_bot:.1%} > P_mkt {p_mkt:.1%} | EV ${ev:+.4f}",
                'phase': self.phase,
            })
        
        self.virtual_balance -= cost
        self._check_phase_progression()
    
    def _execute_live_trade(self, market, side, size, p_bot, p_mkt, ev, price):
        """Execute live trade on CLOB — EV-based"""
        try:
            result = self.order_manager.submit_order(
                market_id=market.id, side='BUY', size=size, confidence=p_bot, price=price,
            )
            if result.get('success'):
                order_id = result.get('order_id', f'live-{time.time()}')
                kelly = self._kelly_or_compute(market.id, p_bot, p_mkt)
                self.portfolio.open_position(
                    position_id=order_id, market_id=market.id, market_name=market.name,
                    side=side, entry_price=price, size=size,
                    kelly_fraction=kelly,
                    market_score=p_bot, confidence=p_bot,
                )
                self.risk_manager.record_trade(0, size)
                logger.info(f"✅ LIVE: Order {order_id} placed")
            else:
                logger.error(f"❌ Live trade failed: {result.get('error')}")
        except Exception as e:
            logger.error(f"❌ Live trade error: {e}")

    # ═══════════════════════════════════════════
    # PORTFOLIO LIFECYCLE
    # ═══════════════════════════════════════════
    
    def _check_portfolio_lifecycle(self):
        """Check all open positions for TP, SL, expiry"""
        if not self.portfolio or not self.portfolio.positions:
            return
        
        # Get current market prices
        market_prices = {}
        market_resolution = {}
        
        if self.polymarket and self.polymarket.is_connected() and self.price_service:
            position_ids = list(self.portfolio.positions.keys())
            market_prices.update(self.price_service.get_batch(position_ids))
        
        if self.paper_trading and not market_prices:
            for pid, pos in self.portfolio.positions.items():
                if self.price_service:
                    self.price_service.record_entry(pid, pos.entry_price)
                    market_prices[pid] = self.price_service.get_price(pid)
                else:
                    import random
                    change = random.uniform(-0.02, 0.03)
                    market_prices[pos.market_id] = max(0.01, min(0.99, pos.entry_price + change))
        
        # Check lifecycle (TP/SL/Expiry)
        to_close = self.portfolio.check_lifecycle(market_prices, market_resolution)
        
        # Phase 6: Risk Offloading check — sell before binary resolution
        if self.compounding and self.portfolio.positions:
            positions_snapshot = list(self.portfolio.positions.items())
            for pos_id, pos in positions_snapshot:
                if pos_id in [tc[0] for tc in to_close]:
                    continue  # Already being closed
                
                # Calculate hours to resolution
                hours_left = float('inf')
                res_info = market_resolution.get(pos.market_id, {})
                res_str = res_info.get('end_date_iso', '')
                if res_str:
                    try:
                        from datetime import timezone
                        res_date = datetime.fromisoformat(res_str.replace("Z", "+00:00"))
                        hours_left = (res_date - datetime.now(res_date.tzinfo)).total_seconds() / 3600
                    except:
                        pass
                
                # Use days_to_resolution as fallback
                if hours_left == float('inf') and hasattr(pos, 'age_minutes'):
                    # Estimate from position age — rough fallback
                    pass
                
                current_price = market_prices.get(pos.market_id, pos.entry_price)
                
                should_offload, offload_reason = self.compounding.check_offload(
                    entry_price=pos.entry_price,
                    current_price=current_price,
                    p_bot_entry=pos.market_score,
                    p_mkt_current=current_price,
                    hours_to_resolution=hours_left,
                    side=pos.side
                )
                
                if should_offload:
                    logger.info(f"📦 Risk Offload: {pos.market_name[:40]} — {offload_reason}")
                    to_close.append((pos_id, f"Risk Offload: {offload_reason}", current_price))
        
        for position_id, reason, exit_price in to_close:
            logger.info(f"🔄 Auto-close: {position_id} — {reason} @ ${exit_price:.3f}")
            self.portfolio.close_position(position_id, exit_price, reason)
    
    def _check_rebalancing(self):
        """Check if portfolio needs rebalancing"""
        if not self.portfolio:
            return
        
        rebalance = self.portfolio.check_rebalance()
        if not rebalance:
            return
        
        action = rebalance.get('action')
        logger.info(f"⚖️ Rebalance needed: {action} — {rebalance.get('reason')}")
        
        if action == 'reduce_largest':
            pos_id = rebalance.get('position_id')
            reduce_pct = rebalance.get('reduce_pct', 0.25)
            # In live: partially close
            # In paper: just log
            logger.info(f"  → Reducing {pos_id} by {reduce_pct*100:.0f}%")
        
        elif action == 'close_lowest_score':
            pos_id = rebalance.get('position_id')
            pos = self.portfolio.positions.get(pos_id)
            if pos:
                exit_price = pos.current_price or pos.entry_price
                self.portfolio.close_position(pos_id, exit_price, "Rebalance: overexposed")

    # ═══════════════════════════════════════════
    # DYNAMIC PHASE PROGRESSION
    # ═══════════════════════════════════════════
    
    def _check_phase_progression(self):
        """Auto-advance phase based on performance"""
        if not self.memory or self.paper_trading:
            return
        
        stats = self.memory.get_trading_stats()
        closed = stats.get('total_closed', 0)
        win_rate = stats.get('win_rate', 0)
        
        if closed < 5:
            return  # Need minimum data
        
        # Phase up criteria
        thresholds = {
            1: {'trades': 5, 'win_rate': 0.65, 'next': 2},
            2: {'trades': 10, 'win_rate': 0.60, 'next': 3},
            3: {'trades': 15, 'win_rate': 0.55, 'next': 4},
        }
        
        criteria = thresholds.get(self.phase)
        if not criteria:
            return  # Already at max
        
        if closed >= criteria['trades'] and win_rate >= criteria['win_rate']:
            new_phase = criteria['next']
            logger.info(f"🚀 PHASE UP! {self.phase} → {new_phase}")
            logger.info(f"   Stats: {closed} trades, {win_rate:.1%} win rate (required: {criteria['win_rate']:.0%})")
            
            self.phase = new_phase
            self.strategy.phase = new_phase
            self.risk_manager.phase = new_phase
            self.portfolio.phase = new_phase
            self.risk_manager.capital = self.current_capital
            
            logger.info(f"   New limits: {self.PHASES[self.phase]['name']} — max {self.PHASES[self.phase]['max_position']*100:.0f}% position")

    # ═══════════════════════════════════════════
    # EFFICIENCY HELPERS
    # ═══════════════════════════════════════════

    def _kelly_or_compute(self, market_id: str, p_bot: float, p_mkt: float) -> float:
        if self.kelly_cache:
            result = self.kelly_cache.get_or_compute(
                market_id, p_bot, p_mkt, LunaStrategy.kelly_fraction,
            )
            return result.fraction
        return LunaStrategy.kelly_fraction(p_bot, p_mkt)

    # ═══════════════════════════════════════════
    # HEALTH & RISK
    # ═══════════════════════════════════════════
    
    def _run_health_check(self) -> dict:
        """Run system health check"""
        if not self.portfolio:
            return {'status': 'critical', 'issues': ['Portfolio not initialized']}
        
        health = self.portfolio.health_check()
        
        # Additional checks
        if self._errors_last_hour >= 5:
            health['status'] = 'critical'
            health['issues'].append(f"{self._errors_last_hour} errors in last hour")
        
        if self.current_capital < 0.50:
            health['status'] = 'critical'
            health['issues'].append(f"Capital critically low: ${self.current_capital:.2f}")
        
        return health
    
    def _check_drawdown(self) -> bool:
        """Check daily drawdown limit"""
        today = datetime.now().date()
        
        if today != self.last_reset:
            self.daily_pnl = 0.0
            self.last_reset = today
            self.risk_manager.reset_session()
            logger.info("📅 New day — daily PnL reset")
        
        # Calculate drawdown from portfolio
        if self.portfolio:
            total_pnl = self.portfolio.total_realized_pnl if hasattr(self.portfolio, 'total_realized_pnl') else self.daily_pnl
            drawdown_pct = abs(total_pnl) / self.current_capital if self.current_capital > 0 else 0
        else:
            drawdown_pct = 0
        
        if drawdown_pct >= self.max_daily_loss_pct:
            logger.warning(f"🛑 Daily drawdown: {drawdown_pct*100:.1f}% (limit: {self.max_daily_loss_pct*100:.0f}%)")
            return False
        
        return True
    
    def _log_session_summary(self):
        """Log current session summary"""
        if not self.portfolio:
            return
        
        summary = self.portfolio.get_portfolio_summary()
        logger.info(f"📊 Portfolio: {summary['open_positions']} open | "
                   f"Exposure: ${summary['total_exposure']:.2f} ({summary['exposure_pct']:.0f}%) | "
                   f"Capital: ${summary['capital']:.2f}")
        
        # Log open positions detail
        details = self.portfolio.get_open_positions_detail()
        for d in details:
            logger.info(f"  → {d['side']} ${d['size']:.2f} @ ${d['entry']:.3f} | "
                       f"PnL: {d['pnl_pct']:+.1f}% | {d['age_hours']:.1f}h | {d['state']}")

    def generate_daily_report(self):
        """Generate daily evolution report & RUN LEARNING CYCLE"""
        try:
            # 1. Evolution Analysis (Phase 3)
            if self.evolution_engine:
                self.evolution_engine.run_analysis(min_trades=10)
                logger.info(f"🧠 EVOLUTION STATE:\n{self.evolution_engine.adjustment_report}")
            
            # 2. Portfolio Stats
            summary = self.portfolio.get_portfolio_summary() if self.portfolio else {}
            stats = self.memory.get_trading_stats()
            
            report = f"""📊 LUNA DAILY REPORT - {datetime.now().strftime('%Y-%m-%d')}

💰 Capital: ${self.current_capital:.2f}
📊 Mode: {'PAPER' if self.paper_trading else 'LIVE'}
🚀 Phase: {self.phase} ({self.PHASES[self.phase]['name']})

📈 Trades: {stats.get('total_trades', 0)} | Wins: {stats.get('winning_trades', 0)} | Losses: {stats.get('losing_trades', 0)}
🏆 Win Rate: {stats.get('win_rate', 0)*100:.1f}%
💵 PnL: ${stats.get('pnl', 0):+.2f} | ROI: {stats.get('roi', 0):+.2f}%

📋 Portfolio: {summary.get('open_positions', 0)} open | ${summary.get('total_exposure', 0):.2f} exposed
⚖️ Exposure: {summary.get('exposure_pct', 0):.0f}% | YES: ${summary.get('yes_exposure', 0):.2f} | NO: ${summary.get('no_exposure', 0):.2f}

Keep compounding! 🌙"""
            
            logger.info(report)
            
            # Save to database
            self.memory.save_daily_evolution({
                'date': datetime.now().strftime('%Y-%m-%d'),
                'starting_capital': self.current_capital,
                'ending_capital': self.current_capital + stats.get('pnl', 0),
                'total_trades': stats.get('total_trades', 0),
                'winning_trades': stats.get('winning_trades', 0),
                'losing_trades': stats.get('losing_trades', 0),
                'win_rate': stats.get('win_rate', 0),
                'roi_percent': stats.get('roi', 0),
                'phase': self.phase,
            })
            
            return report
            
        except Exception as e:
            logger.error(f"❌ Daily report failed: {e}")
            return None

    # ═══════════════════════════════════════════
    # MAIN LOOP
    # ═══════════════════════════════════════════
    
    def run(self):
        """Main bot loop with error recovery"""
        logger.info("=" * 60)
        logger.info("🚀 LUNA BOT PHASE 3 — STARTING")
        logger.info("=" * 60)
        logger.info(f"💰 Capital: ${self.current_capital:.2f}")
        logger.info(f"📊 Mode: {'📝 PAPER' if self.paper_trading else '🔴 LIVE'}")
        logger.info(f"🚀 Phase: {self.phase} — {self.PHASES[self.phase]['name']}")
        logger.info(f"⏱️ Check interval: {self.check_interval}m")
        logger.info(f"🛡️ Max daily loss: {self.max_daily_loss_pct*100:.0f}%")
        logger.info(f"📋 Max positions: {self.risk_manager.session.daily_trades if self.risk_manager else 0}")
        logger.info("=" * 60)
        
        # Schedule
        schedule.every(self.check_interval).minutes.do(self.check_markets)
        schedule.every().day.at("23:55").do(self.generate_daily_report)
        
        # Initial run
        self.check_markets()
        
        self._running = True
        
        # Main loop with error recovery
        while self._running:
            try:
                schedule.run_pending()
                time.sleep(30)
                
                # Emergency: too many errors
                if self._errors_last_hour >= 10:
                    logger.error("🚨 Too many errors — emergency shutdown")
                    self._emergency_shutdown()
                    break
                    
            except KeyboardInterrupt:
                logger.info("👋 Graceful shutdown requested...")
                self.generate_daily_report()
                break
            except Exception as e:
                logger.error(f"❌ Main loop error: {e}")
                logger.error(traceback.format_exc())
                self._errors_last_hour += 1
                time.sleep(60)
    
    def _emergency_shutdown(self):
        """Emergency close all positions"""
        logger.warning("🚨 EMERGENCY SHUTDOWNS — closing all positions")
        if self.portfolio:
            self.portfolio.emergency_close_all()
        self.generate_daily_report()

    def stop(self):
        """Graceful stop"""
        self._running = False


    # ═══════════════════════════════════════════
    # BACKTESTING
    # ═══════════════════════════════════════════

    def run_backtest(self, limit=50, category=None):
        """Run backtest against historical resolved markets"""
        import os
        bt = Backtester(self.strategy, initial_capital=float(os.getenv('BACKTEST_CAPITAL', 100)))
        logger.info(f"🧪 Fetching {limit} resolved markets{' in ' + category if category else ''}...")
        markets = bt.fetch_resolved_markets(category=category, limit=limit)
        logger.info(f"📥 Got {len(markets)} markets, running backtest...")
        result = bt.run(markets)
        report = bt.print_report(result)
        logger.info(report)
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'backtest_result.json')
        bt.save_results(result, path)
        logger.info(f"💾 Results saved to {path}")
        return result

if __name__ == "__main__":
    try:
        bot = LunaTradingBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"💀 Bot crashed: {e}")
        logger.error(traceback.format_exc())
