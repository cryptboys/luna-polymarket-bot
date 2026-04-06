import json
import sys
sys.path.insert(0, "/home/wawan/luna-polymarket-bot")

import requests
from src.polymarket import PolymarketClient

# 1. Raw API check
print("=== RAW API ===")
resp = requests.get(
    "https://gamma-api.polymarket.com/markets",
    params={"limit": 1, "active": "true"},
    timeout=15
)
data = resp.json()[0]
op = data.get("outcomePrices")
print(f"Type: {type(op)}")
print(f"Value repr: {repr(op[:100] if isinstance(op, str) else op)}")
print(f"Outcomes: {data.get('outcomes')}")

# Try json.loads if it's a string
if isinstance(op, str):
    parsed = json.loads(op)
    print(f"After json.loads: type={type(parsed)}, value={parsed}")

# 2. PolymarketClient check
print("\n=== CLIENT ===")
c = PolymarketClient()
markets = c.get_markets(2)
for m in markets:
    print(f"Name: {m.name[:60]}")
    print(f"  outcome_prices: {m.outcome_prices}")
    print(f"  bid={m.best_bid} ask={m.best_ask}")
    print()
