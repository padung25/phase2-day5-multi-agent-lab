"""LLM client abstraction.

Production note: agents should depend on this interface instead of importing an SDK directly.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from multi_agent_research_lab.core.config import Settings, get_settings

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMResponse:
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    provider: str = "offline"
    model: str | None = None


class LLMClient:
    """Provider-agnostic LLM client.

    If `OPENAI_API_KEY` is configured and the `openai` package is installed, calls OpenAI.
    Otherwise it returns a deterministic local completion so development and tests remain
    reproducible without network access.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> LLMResponse:
        """Return a model completion."""

        if self.settings.openai_api_key:
            if _openai_module() is None:
                return self._complete_offline(system_prompt, user_prompt)
            try:
                return self._complete_openai(system_prompt, user_prompt, temperature, max_tokens)
            except Exception:
                LOGGER.exception("OpenAI completion failed; falling back to local completion")
        return self._complete_offline(system_prompt, user_prompt)

    @retry(
        retry=retry_if_exception_type((TimeoutError, ConnectionError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _complete_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        openai_module = _openai_module()
        if openai_module is None:
            raise ModuleNotFoundError("openai")
        client = openai_module.OpenAI(api_key=self.settings.openai_api_key)
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self.settings.timeout_seconds,
        )
        content = response.choices[0].message.content or ""
        usage: Any = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        return LLMResponse(
            content=content.strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=_estimate_openai_cost(self.settings.openai_model, input_tokens, output_tokens),
            provider="openai",
            model=self.settings.openai_model,
        )

    def _complete_offline(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        words = [word.strip() for word in user_prompt.replace("\n", " ").split(" ") if word.strip()]
        summary = " ".join(words[:90])
        content = (
            "Offline completion mode. Configure OPENAI_API_KEY and install the llm extras for "
            "provider-backed output.\n\n"
            f"Task focus: {summary}"
        )
        return LLMResponse(
            content=content,
            input_tokens=_rough_token_count(system_prompt + "\n" + user_prompt),
            output_tokens=_rough_token_count(content),
            provider="offline",
            model="local-deterministic",
        )


def _rough_token_count(text: str) -> int:
    return max(1, len(text.split()) * 4 // 3)


@lru_cache(maxsize=1)
def _openai_module() -> Any | None:
    try:
        return importlib.import_module("openai")
    except ModuleNotFoundError:
        LOGGER.warning("OPENAI_API_KEY is set but the openai package is not installed")
        return None


def _estimate_openai_cost(
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    per_million = {
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
    }
    input_rate, output_rate = per_million.get(model, (0.0, 0.0))
    if input_rate == 0.0 and output_rate == 0.0:
        return None
    return (input_tokens / 1_000_000 * input_rate) + (output_tokens / 1_000_000 * output_rate)
