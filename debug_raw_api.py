#!/usr/bin/env python3
import requests, json

resp = requests.get(
    "https://gamma-api.polymarket.com/markets",
    params={"limit": 2, "active": "true", "order": "volume24hr", "ascending": "false"},
    timeout=30
)
data = resp.json()

for i, m in enumerate(data[:1]):
    print(f"\n=== Market {i} (full keys) ===")
    for k,v in m.items():
        if isinstance(v, (list, dict)):
            print(f"  {k}: {type(v).__name__} (len={len(v)})")
            # Show first item/keys
            if isinstance(v, dict):
                print(f"    keys: {list(v.keys())[:10]}")
            elif v:
                print(f"    [0]: {json.dumps(v[0], indent=2)[:200]}")
        else:
            print(f"  {k}: {v}")
