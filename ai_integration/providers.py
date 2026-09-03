"""Thin REST clients for each supported AI provider. Every call goes through
`AIProvider.chat()`, which never raises -- it always returns an AIResult
(ok / text / error / tokens / latency) so callers (importer.py, the API
layer) can treat "AI failed" as ordinary data, not an exception to catch
everywhere. This is the ONLY module in the codebase that makes outbound
calls to a third-party AI API; nothing in backtest_engine, paper_trading,
or engine.py ever imports this module or any AI provider client."""

import time
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class AIResult:
    ok: bool
    text: str = ""
    error: str = ""
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_ms: int = 0


def _retry_after_seconds(header_value, default):
    """Parses a Retry-After header (seconds, per RFC) -- falls back to
    `default` if missing or not a plain integer (some providers omit it or
    use an HTTP-date form this doesn't bother parsing)."""
    if not header_value:
        return default
    try:
        return max(0, int(header_value))
    except (TypeError, ValueError):
        return default


class AIProvider:
    name = "base"

    def __init__(self, api_key, model, temperature=0.3, max_tokens=4096, timeout=30, retry_count=2):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.retry_count = max(0, retry_count)

    def _build_request(self, system, user):
        raise NotImplementedError

    def _parse_response(self, data):
        raise NotImplementedError

    def chat(self, user, system=None):
        if not self.api_key:
            return AIResult(ok=False, error="No API key configured for this provider.")

        url, headers, body = self._build_request(system, user)
        attempts = self.retry_count + 1
        last_error = "unknown error"

        for attempt in range(attempts):
            start = time.time()
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
                latency_ms = int((time.time() - start) * 1000)
                if resp.status_code >= 400:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                    if resp.status_code in (401, 403):
                        break  # auth errors never succeed on retry
                    # Grand Feature Expansion, Phase 1 Feature 10: 429 (rate
                    # limited) previously fell through to the generic
                    # `continue` below with NO backoff at all, hammering the
                    # provider on every retry instead of waiting -- same
                    # Retry-After-aware pattern data_engine/binance_client.py
                    # already uses for the exchange API.
                    if resp.status_code == 429 and attempt < attempts - 1:
                        wait = _retry_after_seconds(resp.headers.get("Retry-After"), default=5 * (attempt + 1))
                        time.sleep(wait)
                    elif resp.status_code >= 500 and attempt < attempts - 1:
                        time.sleep(2 * (attempt + 1))
                    continue
                text, tin, tout = self._parse_response(resp.json())
                if not text:
                    last_error = "Provider returned an empty response."
                    continue
                return AIResult(ok=True, text=text, tokens_in=tin, tokens_out=tout, latency_ms=latency_ms)
            except requests.Timeout:
                latency_ms = int((time.time() - start) * 1000)
                last_error = f"Request timed out after {self.timeout}s."
                if attempt < attempts - 1:
                    time.sleep(2 * (attempt + 1))
            except requests.RequestException as exc:
                latency_ms = int((time.time() - start) * 1000)
                last_error = f"Network error: {exc}"
                if attempt < attempts - 1:
                    time.sleep(2 * (attempt + 1))
            except (KeyError, IndexError, ValueError) as exc:
                latency_ms = int((time.time() - start) * 1000)
                last_error = f"Unexpected response shape: {exc}"

        return AIResult(ok=False, error=last_error, latency_ms=latency_ms)

    def test_connection(self):
        result = self.chat("Reply with exactly one word: OK", system="You are a connection test.")
        if result.ok:
            return True, f"Connected. Model responded in {result.latency_ms}ms.", result.latency_ms
        return False, result.error, result.latency_ms


class ClaudeProvider(AIProvider):
    name = "claude"

    def _build_request(self, system, user):
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": user}],
        }
        if system:
            body["system"] = system
        return url, headers, body

    def _parse_response(self, data):
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        usage = data.get("usage", {})
        return text, usage.get("input_tokens"), usage.get("output_tokens")


class _OpenAICompatibleProvider(AIProvider):
    """OpenAI, Groq, and DeepSeek all speak the same chat-completions shape."""
    base_url = ""

    def _build_request(self, system, user):
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        return self.base_url, headers, body

    def _parse_response(self, data):
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return text, usage.get("prompt_tokens"), usage.get("completion_tokens")


class OpenAIProvider(_OpenAICompatibleProvider):
    name = "openai"
    base_url = "https://api.openai.com/v1/chat/completions"


class GroqProvider(_OpenAICompatibleProvider):
    name = "groq"
    base_url = "https://api.groq.com/openai/v1/chat/completions"


class DeepSeekProvider(_OpenAICompatibleProvider):
    name = "deepseek"
    base_url = "https://api.deepseek.com/chat/completions"


class GeminiProvider(AIProvider):
    name = "gemini"

    def _build_request(self, system, user):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        body = {
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": self.temperature, "maxOutputTokens": self.max_tokens},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return url, headers, body

    def _parse_response(self, data):
        candidates = data.get("candidates", [])
        text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata", {})
        return text, usage.get("promptTokenCount"), usage.get("candidatesTokenCount")


_PROVIDER_CLASSES = {
    "claude": ClaudeProvider,
    "groq": GroqProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "deepseek": DeepSeekProvider,
}


def get_provider(name, settings):
    """settings: the per-provider dict from ai_integration.config (api_key,
    model, temperature, max_tokens, timeout, retry_count)."""
    cls = _PROVIDER_CLASSES.get(name)
    if not cls:
        raise ValueError(f"Unknown AI provider: {name}")
    return cls(
        api_key=settings.get("api_key", ""),
        model=settings.get("model"),
        temperature=settings.get("temperature", 0.3),
        max_tokens=settings.get("max_tokens", 4096),
        timeout=settings.get("timeout", 30),
        retry_count=settings.get("retry_count", 2),
    )
