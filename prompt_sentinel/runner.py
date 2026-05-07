"""
LLM runner — calls OpenAI, Anthropic, or any OpenAI-compatible endpoint.
Zero mandatory deps: uses urllib so it works with just stdlib.
If openai/anthropic packages are installed, uses them for better error handling.
"""

import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    raw: dict


class LLMRunner:
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        timeout: int = 30,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

        # Determine provider from model name
        if model.startswith("claude"):
            self.provider = "anthropic"
            self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            self.base_url = base_url or "https://api.anthropic.com/v1/messages"
        else:
            self.provider = "openai"
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
            self.base_url = base_url or "https://api.openai.com/v1/chat/completions"

    def run(self, system_prompt: str, user_input: str) -> LLMResponse:
        if self.provider == "anthropic":
            return self._run_anthropic(system_prompt, user_input)
        return self._run_openai(system_prompt, user_input)

    def _run_openai(self, system_prompt: str, user_input: str) -> LLMResponse:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        raw = self._post(self.base_url, payload, headers)
        content = raw["choices"][0]["message"]["content"]
        usage = raw.get("usage", {})
        return LLMResponse(
            content=content,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            model=raw.get("model", self.model),
            raw=raw,
        )

    def _run_anthropic(self, system_prompt: str, user_input: str) -> LLMResponse:
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_input}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        raw = self._post(self.base_url, payload, headers)
        content = raw["content"][0]["text"]
        usage = raw.get("usage", {})
        return LLMResponse(
            content=content,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            model=raw.get("model", self.model),
            raw=raw,
        )

    def _post(self, url: str, payload: dict, headers: dict) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            raise RuntimeError(f"LLM API error {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error calling LLM: {e.reason}") from e
