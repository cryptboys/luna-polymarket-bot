# LLM Router — Free models primary, qwen3.5-flash ONLY when all free models exhausted

import os
import time
import logging

logger = logging.getLogger(__name__)

# Free models ordered by quality (best → good)
FREE_MODELS = [
    "qwen/qwen3-235b-a22b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.0-flash-lite-preview-02-20:free",
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
        self._models = list(FREE_MODELS)
        self._fallback = FALLBACK_MODEL
        self._base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self._api_key = os.getenv("OPENROUTER_API_KEY", "")
        self._blocked_until = {}
        self._idx = 0
        self._calls = 0
        self._fallbacks_used = 0

    def call(self, system, user, max_tokens=256, temperature=0.2) -> str:
        self._calls += 1
        last_err = None

        for _ in range(len(self._models)):
            model = self._models[self._idx % len(self._models)]
            self._idx += 1

            if self._is_blocked(model):
                continue

            try:
                result = self._request(model, system, user, max_tokens, temperature)
                return result
            except RateLimitError:
                last_err = None
                logger.debug(f"Free rate-lim {model.split('/')[-1]}")
            except Exception as e:
                last_err = e
                logger.warning(f"Free err {model.split('/')[-1]}: {e}")

        if not self._fallback_used_recently():
            self._fallbacks_used += 1
            logger.warning(f"All free exhausted, using paid fallback: {self._fallback.split('/')[-1]}")
            try:
                return self._request(self._fallback, system, user, max_tokens, temperature)
            except Exception as e:
                last_err = e

        raise LLMError(
            f"All models failed ({len(self._models)} free + 1 paid). Last: {last_err}"
        )

    def _request(self, model, system, user, max_tokens, temperature):
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
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=60)

        if resp.status_code == 429:
            retry = int(resp.headers.get("Retry-After", 120))
            self._blocked_until[model] = time.time() + retry
            raise RateLimitError()

        if resp.status_code >= 400:
            self._blocked_until[model] = time.time() + 300
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")

        return resp.json()["choices"][0]["message"]["content"].strip()

    def _is_blocked(self, model):
        until = self._blocked_until.get(model)
        if until is None:
            return False
        if time.time() < until:
            return True
        del self._blocked_until[model]
        return False

    def _fallback_used_recently(self):
        until = self._blocked_until.get(self._fallback)
        if until and time.time() < until:
            return True
        return False

    def stats(self):
        return {
            "calls": self._calls,
            "fallbacks": self._fallbacks_used,
            "free_active": len([m for m in self._models if not self._is_blocked(m)]),
            "free_blocked": len([m for m in self._models if self._is_blocked(m)]),
        }


_router = None


def get_llm_router():
    global _router
    if _router is None:
        _router = LlmRouter()
    return _router


def llm_analyze(system, user, max_tokens=256, temperature=0.2):
    return get_llm_router().call(system, user, max_tokens, temperature)
