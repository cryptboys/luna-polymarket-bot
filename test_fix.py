import sys
sys.path.insert(0, "/home/wawan/luna-polymarket-bot")
from src.polymarket import PolymarketClient

c = PolymarketClient()
markets = c.get_markets(3)
for m in markets:
    print(f"Name: {m.name[:60]}")
    print(f"  outcome_prices: {m.outcome_prices}")
    print(f"  bid={m.best_bid} ask={m.best_ask}")
    print(f"  liquidity={m.liquidity} vol={m.volume_24h}")
    print()
