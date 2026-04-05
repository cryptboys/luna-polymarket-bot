# Local Web Dashboard for Luna Bot
# Phase 4: Real-time monitoring via browser (no Telegram needed)

import os
import json
import logging
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# HTML Dashboard template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌙 Luna Bot Dashboard</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🌙</text></svg>">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #e6edf3; min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        
        /* Header */
        .header { text-align: center; padding: 20px 0; border-bottom: 1px solid #30363d; margin-bottom: 30px; }
        .header h1 { font-size: 1.8rem; margin-bottom: 5px; }
        .header .subtitle { color: #8b949e; font-size: 0.9rem; }
        .header .status { display: inline-flex; align-items: center; gap: 8px; margin-top: 10px; padding: 4px 12px; border-radius: 20px; font-size: 0.85rem; }
        .status.healthy { background: #23863633; color: #3fb950; border: 1px solid #238636; }
        .status.warning { background: #d2992233; color: #d29922; border: 1px solid #d29922; }
        .status.critical { background: #da363333; color: #f85149; border: 1px solid #da3633; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        
        /* Grid */
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 30px; }
        
        /* Cards */
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }
        .card h3 { color: #8b949e; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }
        .card .value { font-size: 2rem; font-weight: 700; margin-bottom: 5px; }
        .card .value.positive { color: #3fb950; }
        .card .value.negative { color: #f85149; }
        .card .sub { color: #8b949e; font-size: 0.85rem; }
        
        /* Positions table */
        .positions { overflow-x: auto; }
        .positions table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
        .positions th { background: #0d1117; color: #8b949e; padding: 10px 12px; text-align: left; border-bottom: 1px solid #30363d; font-weight: 500; }
        .positions td { padding: 10px 12px; border-bottom: 1px solid #21262d; }
        .positions tr:hover { background: #1c2129; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
        .badge-yes { background: #23863633; color: #3fb950; }
        .badge-no { background: #da363333; color: #f85149; }
        .badge-open { background: #1f6feb33; color: #58a6ff; }
        
        /* Phase indicator */
        .phase-badge { display: inline-block; padding: 4px 12px; background: #388bfd33; color: #58a6ff; border-radius: 16px; font-weight: 600; font-size: 0.9rem; }
        
        /* Progress bars */
        .progress { height: 6px; background: #21262d; border-radius: 3px; overflow: hidden; margin-top: 8px; }
        .progress-bar { height: 100%; border-radius: 3px; transition: width 0.5s ease; }
        .progress-green { background: #238636; }
        .progress-red { background: #da3633; }
        .progress-yellow { background: #d29922; }
        
        /* Log */
        .log-container { max-height: 300px; overflow-y: auto; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 12px; font-family: 'SF Mono', Monaco, monospace; font-size: 0.8rem; line-height: 1.5; }
        .log-line { padding: 2px 0; border-bottom: 1px solid #161b22; }
        .log-line:last-child { border: none; }
        .log-time { color: #6e7681; }
        .log-info { color: #58a6ff; }
        .log-warn { color: #d29922; }
        .log-error { color: #f85149; }
        
        /* Buttons */
        .btn { display: inline-block; padding: 8px 16px; border-radius: 6px; border: 1px solid #30363d; background: #21262d; color: #e6edf3; cursor: pointer; font-size: 0.85rem; text-decoration: none; margin: 4px; }
        .btn:hover { background: #30363d; }
        .btn-danger { border-color: #da3633; color: #f85149; }
        .btn-danger:hover { background: #da363333; }
        
        /* Auto-refresh */
        .refresh-info { text-align: center; color: #6e7681; font-size: 0.8rem; margin-top: 20px; }
        
        /* Responsive */
        @media (max-width: 768px) {
            .grid { grid-template-columns: 1fr 1fr; }
            .value { font-size: 1.5rem !important; }
        }
        @media (max-width: 480px) {
            .grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>🌙 Luna Bot Dashboard</h1>
            <div class="subtitle">Polymarket Trading Bot — Phase 4</div>
            <div id="status" class="status healthy">
                <span class="status-dot"></span>
                <span id="statusText">Loading...</span>
            </div>
        </div>
        
        <!-- Stats Grid -->
        <div class="grid">
            <div class="card">
                <h3>💰 Capital</h3>
                <div id="capital" class="value">$0.00</div>
                <div id="capitalChange" class="sub"></div>
            </div>
            <div class="card">
                <h3>🚀 Phase</h3>
                <div><span id="phaseBadge" class="phase-badge">Phase 1</span></div>
                <div id="phaseName" class="sub">Safety First</div>
            </div>
            <div class="card">
                <h3>📊 Open Positions</h3>
                <div id="openPositions" class="value">0</div>
                <div class="sub">Exposure: <span id="exposure">$0.00</span> (<span id="exposurePct">0%</span>)</div>
            </div>
            <div class="card">
                <h3>📈 Trade Stats</h3>
                <div id="winRate" class="value">0%</div>
                <div class="sub"><span id="winCount">0W</span> / <span id="lossCount">0L</span> — <span id="totalTrades">0 total</span></div>
            </div>
        </div>
        
        <!-- Exposure breakdown -->
        <div class="grid" style="grid-template-columns: 1fr 1fr;">
            <div class="card">
                <h3>⚖️ Exposure Breakdown</h3>
                <div style="display: flex; gap: 20px; margin-bottom: 10px;">
                    <div>
                        <div class="sub">YES Exposure</div>
                        <div id="yesExposure" class="value" style="font-size:1.2rem; color:#3fb950;">$0</div>
                    </div>
                    <div>
                        <div class="sub">NO Exposure</div>
                        <div id="noExposure" class="value" style="font-size:1.2rem; color:#f85149;">$0</div>
                    </div>
                </div>
                <div class="progress">
                    <div id="exposureBar" class="progress-bar progress-green" style="width: 0%"></div>
                </div>
            </div>
            <div class="card">
                <h3>🔍 Mode</h3>
                <div id="modeValue" class="value" style="font-size:1.3rem">PAPER</div>
                <div id="modeSub" class="sub">No real money at risk</div>
            </div>
        </div>
        
        <!-- Open Positions -->
        <div class="card positions" id="positionsCard" style="margin-bottom: 16px;">
            <h3>📋 Open Positions</h3>
            <table>
                <thead>
                    <tr>
                        <th>Market</th>
                        <th>Side</th>
                        <th>Entry</th>
                        <th>Current</th>
                        <th>PnL %</th>
                        <th>Size</th>
                        <th>Age</th>
                        <th>State</th>
                    </tr>
                </thead>
                <tbody id="positionsBody">
                    <tr><td colspan="8" style="text-align:center; color:#6e7681; padding:20px;">No open positions</td></tr>
                </tbody>
            </table>
        </div>
        
        <!-- Controls -->
        <div style="text-align: center; margin: 20px 0;">
            <button class="btn" onclick="fetchData()">🔄 Refresh Now</button>
            <a class="btn btn-danger" href="/api/emergency">🚨 Emergency Close All</a>
        </div>
        
        <!-- Log -->
        <div class="card">
            <h3>📝 Recent Activity</h3>
            <div class="log-container" id="logContainer">
                <div class="log-line"><span class="log-time">--:--:--</span> <span class="log-info">Waiting for data...</span></div>
            </div>
        </div>
        
        <div class="refresh-info">Auto-refresh every <span id="refreshInterval">10</span> seconds • Last update: <span id="lastUpdate">--:--:--</span></div>
    </div>
    
    <script>
        let refreshTimer = null;
        let previousCapital = 0;
        const REFRESH_INTERVAL = 10000; // 10 seconds
        
        async function fetchData() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                updateDashboard(data);
            } catch (e) {
                console.error('Failed to fetch:', e);
            }
        }
        
        function updateDashboard(data) {
            // Status
            const statusEl = document.getElementById('status');
            const statusText = document.getElementById('statusText');
            statusEl.className = 'status ' + (data.health_status || 'healthy');
            statusText.textContent = data.health_status === 'healthy' ? '✅ Healthy' : 
                                     data.health_status === 'warning' ? '⚠️ Warning' : '🚨 Critical';
            
            // Capital
            document.getElementById('capital').textContent = '$' + (data.capital || 0).toFixed(2);
            if (previousCapital > 0) {
                const change = (data.capital || 0) - previousCapital;
                document.getElementById('capitalChange').textContent = (change >= 0 ? '+' : '') + '$' + change.toFixed(2);
                document.getElementById('capital').className = 'value ' + (change >= 0 ? 'positive' : 'negative');
            }
            previousCapital = data.capital || 0;
            
            // Phase
            document.getElementById('phaseBadge').textContent = 'Phase ' + (data.phase || 1);
            document.getElementById('phaseName').textContent = data.phase_name || 'Safety First';
            
            // Open positions
            document.getElementById('openPositions').textContent = data.open_positions || 0;
            document.getElementById('exposure').textContent = '$' + (data.total_exposure || 0).toFixed(2);
            document.getElementById('exposurePct').textContent = (data.exposure_pct || 0).toFixed(0) + '%';
            
            // Win rate
            document.getElementById('winRate').textContent = ((data.win_rate || 0) * 100).toFixed(1) + '%';
            document.getElementById('winCount').textContent = (data.winning_trades || 0) + 'W';
            document.getElementById('lossCount').textContent = (data.losing_trades || 0) + 'L';
            document.getElementById('totalTrades').textContent = (data.total_trades || 0) + ' total';
            
            // Exposure
            document.getElementById('yesExposure').textContent = '$' + (data.yes_exposure || 0).toFixed(2);
            document.getElementById('noExposure').textContent = '$' + (data.no_exposure || 0).toFixed(2);
            document.getElementById('exposureBar').style.width = Math.min((data.exposure_pct || 0), 100) + '%';
            document.getElementById('exposureBar').className = 'progress-bar ' + 
                ((data.exposure_pct || 0) > 60 ? 'progress-red' : (data.exposure_pct || 0) > 30 ? 'progress-yellow' : 'progress-green');
            
            // Mode
            document.getElementById('modeValue').textContent = (data.paper_trading ? '📝 PAPER' : '🔴 LIVE');
            document.getElementById('modeSub').textContent = data.paper_trading ? 'No real money at risk' : 'Real funds deployed';
            
            // Positions table
            const tbody = document.getElementById('positionsBody');
            if (data.positions && data.positions.length > 0) {
                tbody.innerHTML = data.positions.map(p => {
                    const pnlClass = p.pnl_pct >= 0 ? 'positive' : 'negative';
                    const sideBadge = p.side === 'YES' ? 'badge-yes' : 'badge-no';
                    return `<tr>
                        <td>${p.market || 'Unknown'}</td>
                        <td><span class="badge ${sideBadge}">${p.side}</span></td>
                        <td>$${p.entry.toFixed(3)}</td>
                        <td>$${(p.current || p.entry).toFixed(3)}</td>
                        <td class="${pnlClass}">${p.pnl_pct >= 0 ? '+' : ''}${(p.pnl_pct || 0).toFixed(1)}%</td>
                        <td>$${p.size.toFixed(2)}</td>
                        <td>${(p.age_hours || 0).toFixed(1)}h</td>
                        <td><span class="badge badge-open">${p.state || 'open'}</span></td>
                    </tr>`;
                }).join('');
            } else {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:#6e7681; padding:20px;">No open positions</td></tr>';
            }
            
            // Update time
            const now = new Date();
            document.getElementById('lastUpdate').textContent = now.toLocaleTimeString();
        }
        
        // Auto-refresh
        refreshTimer = setInterval(fetchData, REFRESH_INTERVAL);
        
        // Initial load
        fetchData();
    </script>
</body>
</html>
"""


class DashboardHandler(SimpleHTTPRequestHandler):
    """HTTP handler for the local web dashboard"""
    
    bot_instance = None  # Will be set by bot.py
    
    def log_message(self, format, *args):
        """Suppress default logging to keep bot log clean"""
        pass
    
    def do_GET(self):
        if self.path == '/' or self.path == '/dashboard':
            self.send_html(DASHBOARD_HTML)
        elif self.path == '/api/status':
            self.send_json(self._get_status())
        elif self.path == '/api/emergency':
            self._emergency_close()
            self.send_json({'status': 'emergency_triggered'})
        else:
            self.send_html('<h1>404 Not Found</h1><p>Go to <a href="/">Dashboard</a></p>')
    
    def _get_status(self) -> dict:
        """Get current bot status for API"""
        if not self.bot_instance:
            return {'error': 'Bot not connected'}
        
        bot = self.bot_instance
        portfolio_summary = {}
        positions_detail = []
        
        if bot.portfolio:
            portfolio_summary = bot.portfolio.get_portfolio_summary()
            positions_detail = bot.portfolio.get_open_positions_detail()
        
        health = {'status': 'healthy'}
        if bot.portfolio:
            health = bot.portfolio.health_check()
        
        return {
            'capital': bot.current_capital,
            'initial_capital': bot.initial_capital,
            'phase': bot.phase,
            'phase_name': bot.PHASES.get(bot.phase, {}).get('name', 'Unknown'),
            'paper_trading': bot.paper_trading,
            'virtual_balance': bot.virtual_balance,
            'open_positions': portfolio_summary.get('open_positions', 0),
            'total_exposure': portfolio_summary.get('total_exposure', 0),
            'exposure_pct': portfolio_summary.get('exposure_pct', 0),
            'win_rate': portfolio_summary.get('win_rate', 0),
            'winning_trades': portfolio_summary.get('winning_trades', 0),
            'losing_trades': portfolio_summary.get('losing_trades', 0),
            'total_trades': portfolio_summary.get('closed_positions', 0),
            'yes_exposure': portfolio_summary.get('yes_exposure', 0),
            'no_exposure': portfolio_summary.get('no_exposure', 0),
            'positions': positions_detail,
            'health_status': health.get('status', 'unknown'),
            'check_interval': bot.check_interval,
            'daily_pnl': bot.daily_pnl,
        }
    
    def _emergency_close(self):
        """Trigger emergency close all"""
        if self.bot_instance and self.bot_instance.portfolio:
            closed = self.bot_instance.portfolio.emergency_close_all()
            logger.warning(f"🚨 Emergency closed {len(closed)} positions via dashboard")
    
    def send_html(self, html: str):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def send_json(self, data: dict):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))


def start_dashboard(bot, port: int = 8080) -> Optional[HTTPServer]:
    """
    Start the web dashboard in a background thread.
    Returns server instance or None if failed.
    """
    try:
        DashboardHandler.bot_instance = bot
        
        server = HTTPServer(('0.0.0.0', port), DashboardHandler)
        logger.info(f"🌐 Dashboard started on http://localhost:{port}")
        logger.info(f"   Access from any device on your network: http://<YOUR_IP>:{port}")
        
        return server
        
    except OSError as e:
        if 'Address already in use' in str(e):
            logger.warning(f"⚠️ Port {port} already in use — dashboard disabled")
        else:
            logger.error(f"❌ Failed to start dashboard: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Dashboard error: {e}")
        return None
