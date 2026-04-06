#!/usr/bin/env python3
"""
Luna Polymarket Free Model Auto-Updater — Every 3 Days
Query OpenRouter, quality-rank free models, pick top 5.
Update llm_router.py with new model list.
"""
import requests
import json
import sys
import os
from datetime import datetime

LUNA_DIR = os.path.join(os.path.expanduser("~"), "luna-polymarket-bot")
ROUTER_PATH = os.path.join(LUNA_DIR, "src", "llm_router.py")

# Known good models ranked by reasoning quality
PRIORITY_MODELS = [
    "qwen/qwen3-235b-a22b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "google/gemini-2.0-flash:free",
    "google/gemini-2.0-flash-lite:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "openai/gpt-4o-mini:free",
    "anthropic/claude-3.5-haulette-20241022:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "google/gemma-2-27b-it:free",
]

# Paid fallback — only if all free exhausted
FALLBACK_MODEL = "qwen/qwen3.5-flash-02-23"

def fetch_free_models():
    """Get all free models from OpenRouter."""
    try:
        resp = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"API fetch failed: {e}", file=sys.stderr)
        return []
    
    free = []
    for m in data.get("data", []):
        mid = m.get("id", "")
        if mid.endswith(":free"):
            pricing = m.get("pricing", {})
            free.append({
                "id": mid,
                "name": m.get("name", ""),
                "context": m.get("context_length", 0),
                "prompt_price": float(pricing.get("prompt", 0)),
                "completion_price": float(pricing.get("completion", 0)),
            })
    return free

def score_model(m):
    """Score a model by quality."""
    score = 0
    mid = m["id"].lower()
    full_id = m["id"]
    
    # Priority boost
    if full_id in PRIORITY_MODELS:
        score += 10 - PRIORITY_MODELS.index(full_id)
    
    # Context length bonus
    if m["context"] >= 128000: score += 3
    elif m["context"] >= 32000: score += 2
    elif m["context"] >= 8000: score += 1
    
    # Name heuristic
    if "qwen3" in mid or "qwen3.6" in mid: score += 4
    if "llama" in mid: score += 3
    if "gemini" in mid: score += 2
    if "hermes" in mid: score += 2
    if "claude" in mid: score += 3
    if "deepseek" in mid: score += 2
    
    return score

def update_router(top5):
    """Update llm_router.py with new model list."""
    if not os.path.exists(ROUTER_PATH):
        print(f"Router not found at {ROUTER_PATH}", file=sys.stderr)
        return False
    
    with open(ROUTER_PATH, 'r') as f:
        content = f.read()
    
    # Backup
    backup_path = ROUTER_PATH + ".bak"
    with open(backup_path, 'w') as f:
        f.write(content)
    
    # Replace FREE_MODELS list
    new_list = '\n'.join([f'    "{mid}",' for mid in top5])
    
    # Find and replace the FREE_MODELS list
    import re
    pattern = r'FREE_MODELS = \[[\s\S]*?\]'
    
    replacement = f'FREE_MODELS = [\n{new_list}\n]'
    
    content = re.sub(pattern, replacement, content)
    
    with open(ROUTER_PATH, 'w') as f:
        f.write(content)
    
    return True

def main():
    print(f"[{datetime.now().isoformat()}] Fetching free models from OpenRouter...")
    free_models = fetch_free_models()
    
    if not free_models:
        print("ERROR: No free models found")
        sys.exit(1)
    
    print(f"Found {len(free_models)} free models")
    
    # Score and sort
    scored = [(m, score_model(m)) for m in free_models]
    scored.sort(key=lambda x: -x[1])
    
    # Top 5
    top5 = [m["id"] for m, s in scored[:5]]
    
    print(f"\n=== TOP 5 FREE MODELS (Quality Ranked) ===")
    for i, (m, s) in enumerate(scored[:20], 1):
        ctx = m["context"]
        ctx_str = f"{ctx//1000}k" if ctx else "?"
        print(f"  [{i:2d}] {s:3d}pts | {m['id']} | ctx={ctx_str}")
    
    print(f"\n=== AUTO-SELECTION (Top 5) ===")
    for i, mid in enumerate(top5, 1):
        print(f"  {i}. {mid}")
    print(f"\n  Fallback (paid): {FALLBACK_MODEL}")
    
    # Update router
    if update_router(top5):
        print(f"\n✅ LLM Router updated successfully")
        print(f"   Models: {', '.join(top5)}")
    else:
        print(f"\n❌ Failed to update LLM Router")
        sys.exit(1)

if __name__ == "__main__":
    main()
