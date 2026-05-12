"""Anthropic provider for Claude models (direct API or Bedrock)."""

from __future__ import annotations

import os
from typing import Any

from refusalbench.providers.base import Provider, ProviderError


class AnthropicProvider(Provider):
    """Calls Claude models via the Anthropic API.

    Requires the ``anthropic`` package (``pip install refusalbench[providers]``)
    and ``ANTHROPIC_API_KEY`` environment variable.

    Parameters
    ----------
    api_key:
        Override the ``ANTHROPIC_API_KEY`` env var.
    max_retries:
        Number of automatic retries on transient errors.

    Example
    -------
    >>> # Requires ANTHROPIC_API_KEY
    >>> provider = AnthropicProvider()
    >>> provider  # doctest: +ELLIPSIS
    <refusalbench.providers.anthropic.AnthropicProvider object at ...>
    """

    def __init__(
        self,
        api_key: str | None = None,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._max_retries = max_retries

    def _client(self) -> Any:
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderError(
                "anthropic package required: pip install 'refusalbench[providers]'"
            ) from exc
        if not self._api_key:
            raise ProviderError("ANTHROPIC_API_KEY environment variable not set")
        return anthropic.AsyncAnthropic(
            api_key=self._api_key,
            max_retries=self._max_retries,
        )

    async def complete(
        self,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call Anthropic and return the text response."""
        client = self._client()
        try:
            import anthropic

            message = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            content = message.content[0]
            return str(content.text) if hasattr(content, "text") else ""
        except anthropic.APIError as exc:
            raise ProviderError(f"Anthropic API error: {exc}") from exc
