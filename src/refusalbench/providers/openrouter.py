"""OpenRouter provider (OpenAI-compatible API).

Supports DeepSeek, Qwen, GLM, Mistral, and Anthropic models.
"""

from __future__ import annotations

import os
from typing import Any

from refusalbench.providers.base import Provider, ProviderError

_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_SITE_URL = "https://github.com/VibeCodingScientist/refusalbench"
_DEFAULT_APP_TITLE = "RefusalBench"


class OpenRouterProvider(Provider):
    """Wraps the OpenRouter API using the openai SDK.

    Requires the ``openai`` package (``pip install refusalbench[providers]``)
    and the ``OPENROUTER_API_KEY`` environment variable.

    Parameters
    ----------
    api_key:
        Override the ``OPENROUTER_API_KEY`` env var.
    max_retries:
        Number of automatic retries on transient errors.

    Example
    -------
    >>> # Requires OPENROUTER_API_KEY
    >>> provider = OpenRouterProvider()
    >>> provider  # doctest: +ELLIPSIS
    <refusalbench.providers.openrouter.OpenRouterProvider object at ...>
    """

    def __init__(
        self,
        api_key: str | None = None,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._max_retries = max_retries

    def _client(self) -> Any:
        try:
            import openai
        except ImportError as exc:
            raise ProviderError(
                "openai package required: pip install 'refusalbench[providers]'"
            ) from exc
        if not self._api_key:
            raise ProviderError("OPENROUTER_API_KEY environment variable not set")
        return openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url=_BASE_URL,
            max_retries=self._max_retries,
            default_headers={
                "HTTP-Referer": _DEFAULT_SITE_URL,
                "X-Title": _DEFAULT_APP_TITLE,
            },
        )

    async def complete(
        self,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call OpenRouter and return the assistant message content."""
        client = self._client()
        try:
            import openai

            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            # Guard: some providers (OpenAI, Anthropic) return choices=None
            # or an empty list for API-level refusals rather than a choice
            # with content=None. Both map to the shared sentinel.
            if not response.choices:
                return "[CONTENT_FILTERED]"
            choice = response.choices[0]
            content = choice.message.content
            # Anthropic models on OpenRouter surface API-level refusals as
            # content=None with native_finish_reason="refusal". OpenAI models
            # may return choices=None (caught above) or content=None here.
            # Either way emit the shared sentinel so the council fast-path
            # records direct_refusal/safety_policy without routing to judges.
            if content is None:
                return "[CONTENT_FILTERED]"
            return str(content)
        except openai.APIError as exc:
            raise ProviderError(f"OpenRouter API error: {exc}") from exc
