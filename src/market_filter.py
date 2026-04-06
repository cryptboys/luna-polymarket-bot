from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple, Optional
import logging

logger = logging.getLogger(__name__)


class RejectReason(Enum):
    DURATION_TOO_LONG = "Duration exceeds max"
    LOW_LIQUIDITY = "Liquidity below threshold"
    LOW_VOLUME = "24h volume insufficient"
    SPREAD_TOO_WIDE = "Bid-ask spread too large"
    MARKET_TOO_OLD = "Market age exceeds threshold"
    INVALID_PRICES = "Invalid bid/ask prices"


class GateResult(NamedTuple):
    passed: bool
    reason: Optional[RejectReason] = None
    duration_score: float = 0.0


@dataclass
class MarketFilterConfig:
    max_duration_hours: int = 720   # 30 days (lebih fleksibel untuk paper trade)
    min_liquidity: float = 1000.0   # dari 5000 → cukup untuk $5 modal
    min_volume_24h: float = 500.0   # dari 1000 → cari market aktif tapi nggak terlalu ketat
    max_spread_bps: int = 500       # dari 200 (2%) → 5% (lebih toleran)


class MarketFilter:
    __slots__ = ("config",)

    def __init__(self, config: MarketFilterConfig | None = None) -> None:
        self.config = config or MarketFilterConfig()

    def gate(
        self,
        *,
        hours_to_resolution: float,
        liquidity: float,
        volume_24h: float,
        best_bid: float,
        best_ask: float,
        market_age_days: int = 0,
    ) -> GateResult:
        if best_bid <= 0 or best_ask <= 0 or best_ask <= best_bid:
            return GateResult(False, RejectReason.INVALID_PRICES)

        if hours_to_resolution <= 0 or hours_to_resolution > self.config.max_duration_hours:
            return GateResult(False, RejectReason.DURATION_TOO_LONG)

        if liquidity < self.config.min_liquidity:
            return GateResult(False, RejectReason.LOW_LIQUIDITY)

        if volume_24h < self.config.min_volume_24h:
            return GateResult(False, RejectReason.LOW_VOLUME)

        spread_bps = (best_ask - best_bid) / ((best_bid + best_ask) / 2) * 10_000
        if spread_bps > self.config.max_spread_bps:
            return GateResult(False, RejectReason.SPREAD_TOO_WIDE)

        duration_score = self._duration_score(hours_to_resolution)

        return GateResult(True, None, duration_score)

    @staticmethod
    def _duration_score(hours: float) -> float:
        if hours <= 1:
            return 1.0
        if hours <= 6:
            return 0.95
        if hours <= 24:
            return 0.85
        if hours <= 72:
            return 0.75
        if hours <= 168:
            return 0.60
        return 0.10

    def gate_count_summary(self, total: int, passed: int) -> str:
        rejected = total - passed
        pct = (rejected / total * 100) if total > 0 else 0
        return f"Filter: {passed}/{total} passed ({pct:.0f}% rejected)"
