#!/usr/bin/env python3
import sys, os, json
sys.path.insert(0, '/home/wawan/luna-polymarket-bot')

import requests
from src.polymarket import PolymarketClient

client = PolymarketClient()
markets = client.get_markets(limit=5)

if markets:
    print(f"\n✅ Got {len(markets)} markets")
    for i, m in enumerate(markets[:3]):
        print(f"\n--- Market {i+1} ---")
        print(f"  Name: {m.name[:80]}")
        print(f"  Category: {m.category}")
        print(f"  Liquidity: {m.liquidity}")
        print(f"  Volume 24h: {m.volume_24h}")
        print(f"  Best Bid: {m.best_bid}")
        print(f"  Best Ask: {m.best_ask}")
        print(f"  Days to resolution: {m.days_to_resolution}")
        print(f"  Outcome prices: {m.outcome_prices}")
        print(f"  Slug: {m.slug}")
else:
    print("No markets returned")
