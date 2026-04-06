# Weekly Free Model Selector
# Queries OpenRouter API, finds available free models, updates llm_router.py
import os
import json
import re
import logging

logger = logging.getLogger(__name__)

PREFERRED_FREE_ORDER = [
    ("qwen/qwen3-235b-a22b", 10),
    ("qwen/qwen-2.5-72b-instruct", 9),
    ("meta-llama/llama-3.3-70b-instruct", 9),
    ("google/gemini-2.0-flash-lite-preview-02-20", 8),
    ("google/gemini-flash-1.5-8b", 7),
    ("nousresearch/hermes-3-llama-3.1-405b", 8),
    ("meta-llama/llama-3.1-405b-instruct", 8),
    ("qwen/qwen3-14b", 6),
    ("google/gemma-2-27b", 6),
    ("mistralai/mistral-small-3.1-24b-instruct", 7),
]


def fetch_free_models():
    """Query OpenRouter for all currently available free models"""
    import requests
    resp = requests.get("https://openrouter.ai/api/v1/models", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    models = data.get("data", [])

    free_models = []
    for m in models:
        model_id = m.get("id", "")
        pricing = m.get("pricing", {})
        is_free = model_id.endswith(":free") or (
            all(float(v) == 0 for v in pricing.values()) if pricing else False
        )
        if is_free and not model_id.endswith(":free"):
            model_id = f"{model_id}:free"

        context = m.get("context_length", 0)
        free_models.append({
            "id": model_id,
            "name": m.get("name", ""),
            "context": context,
        })
    return free_models


def select_best_available(all_free, max_models=5):
    """Pick best available free models based on preferred list"""
    available_ids = {m["id"] for m in all_free}

    selected = []
    remaining = []
    for model_id, priority in PREFERRED_FREE_ORDER:
        if len(selected) >= max_models:
            break
        free_id = f"{model_id}:free" if not model_id.endswith(":free") else model_id
        if free_id in available_ids:
            selected.append(free_id)
        else:
            remaining.append((model_id, priority))

    if len(selected) < max_models:
        for m in all_free:
            if len(selected) >= max_models:
                break
            if m["id"] not in selected:
                selected.append(m["id"])

    return selected


def update_llm_router(selected_models):
    """Rewrite FREE_MODELS list in llm_router.py"""
    path = os.path.join(os.path.dirname(__file__), "llm_router.py")

    with open(path, "r") as f:
        content = f.read()

    lines = ",\n".join(f'    "{m}"' for m in selected_models)
    new_list = f"FREE_MODELS = [\n{lines},\n]"

    pattern = r"FREE_MODELS\s*=\s*\[[\s\S]*?\]"
    updated = re.sub(pattern, new_list, content, count=1)

    with open(path, "w") as f:
        f.write(updated)

    return path


def run():
    logger.info("Fetching available free models from OpenRouter...")
    all_free = fetch_free_models()
    logger.info(f"Found {len(all_free)} free models")

    selected = select_best_available(all_free, max_models=5)
    logger.info(f"Selected {len(selected)} best free models:")
    for m in selected:
        logger.info(f"  ✓ {m}")

    path = update_llm_router(selected)
    logger.info(f"Updated {path}")

    # Reset llm_router module if already loaded
    import importlib
    import sys
    key = "src.llm_router" if "src.llm_router" in sys.modules else "llm_router"
    if key in sys.modules:
        importlib.reload(sys.modules[key])
        import src.llm_router as lr
    else:
        from src import llm_router as lr

    if hasattr(lr, "_router") and lr._router:
        lr._router._models = list(selected)
        lr.get_llm_router()._models = list(selected)
        lr.get_llm_router()._blocked_until.clear()

    return selected


if __name__ == "__main__":
    run()
