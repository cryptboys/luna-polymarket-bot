# LLM Router — Multi-model with automatic fallback
# Primary: free models → Fallback: qwen3.5-flash on rate limit/error

import os
import time
import json
import logging

logger = logging.getLogger(__name__)

FREE_MODELS = [
    "qwen/qwen-2.5-72b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-flash-1.5-8b:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
]

FALLBACK_MODEL = "qwen/qwen3.5-flash-02-23"

class LLMError(Exception):
    pass

class RateLimitError(LLMError):
    pass

class LlmRouter:
    def __init__(self):
        self._model_order = list(FREE_MODELS)
        self._fallback = FALLBACK_MODEL
        self._base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self._api_key = os.getenv("OPENROUTER_API_KEY", "")
        self._failure_counts = {}
        self._retry_after = {}
        self._current_primary_idx = 0
        self._call_count = 0
        self._fail_count = 0

    def call(
        self,
        system_prompt,
        user_prompt,
        max_tokens=512,
        temperature=0.3,
    ) -> str:
        self._call_count += 1
        last_error = None

        for attempt in range(2):
            if attempt == 0:
                model = self._select_primary()
            else:
                model = self._fallback

            if model in self._retry_after and time.time() < self._retry_after[model]:
                continue

            try:
                result = self._do_request(model, system_prompt, user_prompt, max_tokens, temperature)
                self._record_success(model)
                return result
            except RateLimitError as e:
                self._record_rate_limit(model)
                last_error = e
                logger.warning(f"Rate limited on {model.split('/')[-1]}, trying next")
            except Exception as e:
                self._record_failure(model)
                last_error = e
                logger.warning(f"Error on {model.split('/')[-1]}: {e}")

        raise LLMError(
            f"All models failed (primary + fallback). "
            f"Last error: {last_error}. Calls:{self._call_count} Fails:{self._fail_count}"
        )

    def _do_request(self, model, system_prompt, user_prompt, max_tokens, temperature):
        import requests
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/cryptboys/luna-polymarket-bot",
            "X-Title": "Luna Polymarket Bot",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            self._retry_after[model] = time.time() + retry_after
            raise RateLimitError(f"Rate limited: {retry_after}s")
        
        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def _select_primary(self) -> str:
        for i in range(len(self._model_order)):
            idx = (self._current_primary_idx + i) % len(self._model_order)
            model = self._model_order[idx]
            if model not in self._retry_after or time.time() >= self._retry_after[model]:
                self._current_primary_idx = (idx + 1) % len(self._model_order)
                return model
        return self._fallback

    def _record_success(self, model):
        self._failure_counts[model] = self._failure_counts.get(model, 0) * 0.9
        if model in self._retry_after and time.time() >= self._retry_after[model]:
            del self._retry_after[model]

    def _record_failure(self, model):
        self._failure_counts[model] = self._failure_counts.get(model, 0) + 1
        self._fail_count += 1
        if self._failure_counts.get(model, 0) >= 3:
            self._retry_after[model] = time.time() + 300

    def _record_rate_limit(self, model):
        self._failure_counts[model] = self._failure_counts.get(model, 0) + 5
        self._fail_count += 1

    def stats(self) -> dict:
        available = [m.split('/')[-1] for m in self._model_order if m not in self._retry_after]
        return {
            "calls": self._call_count,
            "failures": self._fail_count,
            "primary_available": available,
            "primary_unavailable": [m.split('/')[-1] for m in self._model_order if m in self._retry_after],
        }

# Singleton
_router = None

def get_llm_router():
    global _router
    if _router is None:
        _router = LlmRouter()
    return _router

def llm_analyze(system_prompt, user_prompt, max_tokens=512, temperature=0.3):
    return get_llm_router().call(system_prompt, user_prompt, max_tokens, temperature)
