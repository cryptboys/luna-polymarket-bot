"""Telegram notifier for Luna Polymarket bot — PnL & profit reports."""
from __future__ import annotations

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send trading updates to Papi via Telegram bot."""

    def __init__(self) -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self._last_report_hash: str | None = None
        if not self.token or not self.chat_id:
            logger.warning("Telegram bot token or chat_id not set — notifications disabled")

    # ── public API ──────────────────────────────────────────────

    def send(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a message. Returns True on success."""
        if not self.token or not self.chat_id:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                return True
            logger.error(f"Telegram send failed ({resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
        return False

    def send_daily_pnl(
        self,
        capital: float,
        daily_pnl: float,
        total_trades: int,
        wins: int,
        losses: int,
        win_rate: float,
        open_positions: int,
        paper_mode: bool,
        phase_name: str,
        filters_passed: str = "",
        scanning_cycles: int = 0,
    ) -> bool:
        """Format & send the daily PnL digest."""
        emoji = "📝" if paper_mode else "🔴"
        mode_label = "PAPER TRADING" if paper_mode else "LIVE TRADING"

        pnl_emoji = "🟢" if daily_pnl >= 0 else "🔴"

        msg = f"""🌙 *Luna Daily PnL Report* {emoji}

📊 Mode: {mode_label} | Phase: {phase_name}
💰 Capital: *${capital:.2f}*
{pnl_emoji} Daily PnL: *${daily_pnl:+.2f}*

📈 Today's Trades: {total_trades}
   Wins: 🟢 {wins} | Losses: 🔴 {losses}
🏆 Win Rate: {win_rate:.1f}%

📋 Open Positions: {open_positions}"""

        if scanning_cycles > 0:
            msg += f"\n🔍 Scanning: {scanning_cycles} cycles"
        if filters_passed:
            msg += f"\n🚧 Filter: {filters_passed}"

        msg += "\n\n_Keep compounding!_ 💜"

        return self.send(msg)

    def send_scanning_alert(
        self,
        total: int,
        passed: int,
        scanning_cycles: int,
        capital: float,
    ) -> bool:
        """Send a quick scanning summary (every N cycles)."""
        msg = f"""🌙 *Luna Scanning Update*

🔍 {scanning_cycles} cycles | Fetched {total}/cycle
🚧 {passed}/{total} passed filter
💰 Capital: ${capital:.2f}

_No eligible trades found yet or all HOLDs. Bot is collecting data._ 💜"""

        return self.send(msg)

    def send_trade_alert(
        self,
        market_name: str,
        side: str,
        size: float,
        entry_price: float,
        ev: float,
        p_bot: float,
        p_mkt: float,
        capital: float,
    ) -> bool:
        """Send instant notification when a trade is executed."""
        emoji = "✅" if side == "YES" else "❌"
        msg = f"""{emoji} *NEW TRADE OPENED* 🌙

📊 {market_name[:60]}
Direction: *{side}*
Entry: ${entry_price:.4f} | Size: *${size:.2f}*
EV: *${ev:+.4f}* | Edge: {p_bot - p_mkt:+.1%}
P_bot: {p_bot:.1%} vs P_mkt: {p_mkt:.1%}
💰 Capital: ${capital:.2f}

_Risk-managed by Luna_ 🛡️"""

        return self.send(msg)

    def send_error_alert(self, error_text: str) -> bool:
        """Send error/critical alert."""
        msg = f"🚨 *Luna Error Alert*\n\n```{error_text[:400]}```"
        return self.send(msg)
