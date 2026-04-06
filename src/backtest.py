# Backtesting Engine — validate strategy against historical Polymarket data
# Uses Gamma API to fetch resolved markets, runs EV scoring, reports accuracy

import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    market_id: str
    market_name: str
    category: str
    side: str  # YES or NO
    entry_price: float
    p_bot: float
    p_mkt: float
    ev: float
    kelly_fraction: float
    outcome: float  # 0 or 1
    result: str  # "win" or "loss"
    pnl: float
    resolution_date: str


@dataclass
class BacktestResult:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    max_win: float
    max_loss: float
    sharpe: float
    category_breakdown: Dict[str, dict] = field(default_factory=dict)
    trades: List[BacktestTrade] = field(default_factory=list)


class Backtester:
    """Evaluate strategy quality against historical resolved markets"""

    def __init__(self, strategy, initial_capital: float = 100.0):
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.gamma_host = "https://gamma-api.polymarket.com"

    def fetch_resolved_markets(
        self,
        category: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fetch resolved market data from Gamma API"""
        import requests

        url = f"{self.gamma_host}/markets"
        params = {
            "limit": limit,
            "offset": offset,
            "closed": "true",
            "order": "end_date_iso",
        }
        if category:
            params["tag_slug"] = category

        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def run(self, markets: List[Dict[str, Any]]) -> BacktestResult:
        """Run backtest on historical market data"""
        trades = []
        wins = 0
        losses = 0
        total_pnl = 0.0
        ppls = []
        by_category = {}

        for m in markets:
            ev_result = self._evaluate_market(m)
            if ev_result is None:
                continue

            trade = BacktestTrade(**ev_result)
            trades.append(trade)

            if trade.result == "win":
                wins += 1
            else:
                losses += 1

            pnl_usd = trade.pnl
            total_pnl += pnl_usd
            ppls.append(pnl_usd)

            cat = trade.category
            if cat not in by_category:
                by_category[cat] = {"trades": 0, "wins": 0, "pnl": 0.0}
            by_category[cat]["trades"] += 1
            if trade.result == "win":
                by_category[cat]["wins"] += 1
            by_category[cat]["pnl"] += pnl_usd

        n = len(trades)
        win_rate = wins / n if n > 0 else 0.0
        avg_pnl = total_pnl / n if n > 0 else 0.0
        max_w = max(ppls) if ppls else 0.0
        max_l = min(ppls) if ppls else 0.0

        avg_ret = avg_pnl / self.initial_capital if self.initial_capital > 0 else 0
        std_ret = (
            (sum((p / self.initial_capital - avg_ret) ** 2 for p in ppls) / n) ** 0.5
            if n > 1 and self.initial_capital > 0
            else 0
        )
        sharpe = avg_ret / std_ret if std_ret > 0 else 0.0

        return BacktestResult(
            total_trades=n,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            total_pnl=total_pnl,
            avg_pnl=avg_pnl,
            max_win=max_w,
            max_loss=max_l,
            sharpe=sharpe,
            category_breakdown=by_category,
            trades=trades,
        )

    def _evaluate_market(self, market: Dict[str, Any]) -> Optional[dict]:
        """Score a resolved market using strategy, determine what would've happened"""
        try:
            closed_data = market.get("outcome_prices", {})
            if not closed_data:
                return None

            outcome_values = [float(v) for v in closed_data.values() if v is not None]
            if len(outcome_values) < 2:
                return None

            market_id = market.get("id", "")
            name = market.get("question", market.get("slug", ""))
            category = market.get("tag_slug", "unknown")
            resolution_date = market.get("end_date_iso", "")

            best_bid = float(market.get("best_bid", 0) or 0)
            best_ask = float(market.get("best_ask", 1) or 1)
            if best_bid == 0 and best_ask == 1:
                mid = sum(outcome_values) / len(outcome_values) if outcome_values else 0.5
                best_bid = mid - 0.02
                best_ask = mid + 0.02

            market_data = {
                "id": market_id,
                "name": name,
                "category": category,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "liquidity": float(market.get("liquidity", 0) or 0),
                "volume_24h": float(market.get("volume", 0) or 0),
                "price_change_24h": 0.0,
                "days_to_resolution": 0,
                "market_age_days": 0,
                "volume_trend": "neutral",
                "slug": market.get("slug", ""),
            }

            ev_result = self.strategy.analyze_market(market_data)
            if ev_result.action != "BUY":
                return None

            p_bot = ev_result.p_bot
            p_mkt = ev_result.p_mkt
            edge = ev_result.edge

            if p_bot > p_mkt:
                side = "YES"
                entry_price = p_mkt
                winning_price = 1.0
            else:
                side = "NO"
                entry_price = 1 - p_mkt
                winning_price = 1 - p_mkt

            outcome = max(outcome_values)
            if outcome > 0.5 and side == "YES":
                result = "win"
                pnl = winning_price - entry_price
            elif outcome < 0.5 and side == "NO":
                result = "win"
                pnl = winning_price - entry_price
            else:
                result = "loss"
                pnl = -entry_price

            kelly_fraction = self.strategy.kelly_fraction(p_bot, p_mkt)

            return {
                "market_id": market_id,
                "market_name": name[:80],
                "category": category,
                "side": side,
                "entry_price": round(entry_price, 4),
                "p_bot": round(p_bot, 4),
                "p_mkt": round(p_mkt, 4),
                "ev": round(ev_result.ev, 4),
                "kelly_fraction": round(kelly_fraction, 4),
                "outcome": outcome,
                "result": result,
                "pnl": round(pnl, 4),
                "resolution_date": resolution_date,
            }

        except Exception as e:
            logger.debug(f"Backtest eval failed: {e}")
            return None

    def print_report(self, result: BacktestResult) -> str:
        lines = [
            "═══════════════════════════════════════",
            "🧪 BACKTEST REPORT",
            "═══════════════════════════════════════",
            f"Trades analyzed: {result.total_trades}",
            f"Win rate:        {result.win_rate:.1%} ({result.wins}W / {result.losses}L)",
            f"Total PnL:       ${result.total_pnl:+.2f}",
            f"Avg PnL/trade:   ${result.avg_pnl:+.4f}",
            f"Max win:         ${result.max_w:+.4f}",
            f"Max loss:        ${result.max_loss:+.4f}",
            f"Sharpe:          {result.sharpe:.3f}",
            "",
            "── By Category ──",
        ]
        for cat, stats in sorted(
            result.category_breakdown.items(), key=lambda x: x[1]["trades"], reverse=True
        ):
            wr = stats["wins"] / stats["trades"] if stats["trades"] > 0 else 0
            lines.append(f"  {cat:15s} {stats['trades']:3d} trades  {wr:.0%} win  ${stats['pnl']:+.2f}")

        lines.append("═══════════════════════════════════════")
        return "\n".join(lines)

    def save_results(self, result: BacktestResult, path: str) -> None:
        data = {
            "generated_at": datetime.now().isoformat(),
            "initial_capital": self.initial_capital,
            "total_trades": result.total_trades,
            "wins": result.wins,
            "losses": result.losses,
            "win_rate": result.win_rate,
            "total_pnl": result.total_pnl,
            "avg_pnl": result.avg_pnl,
            "max_win": result.max_win,
            "max_loss": result.max_loss,
            "sharpe": result.sharpe,
            "category_breakdown": result.category_breakdown,
            "trades": [
                {
                    "market_id": t.market_id,
                    "market_name": t.market_name,
                    "category": t.category,
                    "side": t.side,
                    "p_bot": t.p_bot,
                    "p_mkt": t.p_mkt,
                    "ev": t.ev,
                    "result": t.result,
                    "pnl": t.pnl,
                    "resolution_date": t.resolution_date,
                }
                for t in result.trades
            ],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Backtest results saved to {path}")
