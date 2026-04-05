from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List
import logging
import time
import math
import random

logger = logging.getLogger(__name__)


class PriceProvider(ABC):
    @abstractmethod
    def get_current_price(self, market_id: str, token_id: str = "") -> float:
        ...

    @abstractmethod
    def batch_prices(self, market_ids: List[str]) -> Dict[str, float]:
        ...


class GammaPriceProvider(PriceProvider):
    def __init__(self, gamma_host: str = "https://gamma-api.polymarket.com") -> None:
        self.gamma_host = gamma_host

    def get_current_price(self, market_id: str, token_id: str = "") -> float:
        import requests
        url = f"{self.gamma_host}/markets/{market_id}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            data = data[0]
        outcome_prices = data.get("outcome_prices", {})
        if not outcome_prices:
            return 0.5
        values = [float(v) for v in outcome_prices.values() if v]
        return sum(values) / len(values) if values else 0.5

    def batch_prices(self, market_ids: List[str]) -> Dict[str, float]:
        result = {}
        for mid in market_ids:
            try:
                result[mid] = self.get_current_price(mid)
                time.sleep(0.15)
            except Exception as e:
                logger.warning(f"Gamma price fetch failed for {mid}: {e}")
                result[mid] = 0.5
        return result


class PaperPriceProvider(PriceProvider):
    def __init__(self, volatility: float = 0.008) -> None:
        self.volatility = volatility
        self._price_log: Dict[str, List[float]] = {}

    def get_current_price(self, market_id: str, token_id: str = "") -> float:
        if market_id not in self._price_log:
            return 0.5
        history = self._price_log[market_id]
        last = history[-1]
        drift = 0.0
        shock = random.gauss(0, self.volatility)
        new_price = last + drift + shock
        new_price = max(0.01, min(0.99, new_price))
        history.append(new_price)
        if len(history) > 100:
            history.pop(0)
        return new_price

    def set_entry_price(self, market_id: str, entry_price: float) -> None:
        if market_id not in self._price_log:
            self._price_log[market_id] = [entry_price]
        else:
            self._price_log[market_id].append(entry_price)

    def batch_prices(self, market_ids: List[str]) -> Dict[str, float]:
        result = {}
        for mid in market_ids:
            if mid in self._price_log:
                result[mid] = self.get_current_price(mid)
            else:
                result[mid] = 0.5
        return result


class PriceService:
    def __init__(
        self,
        gamma_provider: PriceProvider,
        paper_provider: PriceProvider,
        use_paper: bool = True,
    ) -> None:
        self.gamma = gamma_provider
        self.paper = paper_provider
        self.use_paper = use_paper

    def get_price(self, market_id: str, token_id: str = "") -> float:
        if self.use_paper:
            return self.paper.get_current_price(market_id, token_id)
        return self.gamma.get_current_price(market_id, token_id)

    def get_batch(self, market_ids: List[str]) -> Dict[str, float]:
        if self.use_paper:
            return self.paper.batch_prices(market_ids)
        return self.gamma.batch_prices(market_ids)

    def record_entry(self, market_id: str, entry_price: float) -> None:
        if isinstance(self.paper, PaperPriceProvider):
            self.paper.set_entry_price(market_id, entry_price)
