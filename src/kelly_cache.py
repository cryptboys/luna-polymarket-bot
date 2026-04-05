from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Callable, Optional

import logging

logger = logging.getLogger(__name__)


@dataclass
class KellyResult:
    fraction: float
    raw_kelly: float
    p_bot: float
    p_mkt: float


class KellyCache:
    _cache: Dict[str, KellyResult]

    def __init__(self) -> None:
        self._cache = {}
        self._hits = 0
        self._misses = 0

    def get_or_compute(
        self,
        market_id: str,
        p_bot: float,
        p_mkt: float,
        compute_fn: Callable[[float, float], float],
    ) -> KellyResult:
        p_bot_r = round(p_bot, 4)
        p_mkt_r = round(p_mkt, 4)
        key = f"{market_id}:{p_bot_r}:{p_mkt_r}"

        if key in self._cache:
            self._hits += 1
            return self._cache[key]

        self._misses += 1
        frac = compute_fn(p_bot, p_mkt)
        raw = self._invert_kelly(frac, p_mkt) if frac > 0 else 0.0

        result = KellyResult(
            fraction=frac,
            raw_kelly=raw,
            p_bot=p_bot,
            p_mkt=p_mkt,
        )
        self._cache[key] = result
        return result

    @staticmethod
    def _invert_kelly(fractional: float, p_mkt: float) -> float:
        if fractional <= 0 or p_mkt <= 0 or p_mkt >= 1:
            return 0.0
        b = (1.0 - p_mkt) / p_mkt
        return fractional / 0.25 if b > 0 else 0.0

    def clear_cycle(self) -> None:
        self._hits = 0
        self._misses = 0
        self._cache.clear()

    def stats(self) -> Dict[str, object]:
        total = self._hits + self._misses
        rate = (self._hits / total * 100) if total > 0 else 0.0
        return {"hits": self._hits, "misses": self._misses, "hit_rate": f"{rate:.0f}%"}
