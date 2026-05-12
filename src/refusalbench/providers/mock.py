"""Mock provider returning preset responses. Used by tests and demo."""

from __future__ import annotations

from refusalbench.providers.base import Provider


class MockProvider(Provider):
    """Returns a fixed response string for every call.

    Parameters
    ----------
    response:
        The string to return for every ``complete`` call.

    Example
    -------
    >>> import asyncio
    >>> p = MockProvider("Here is the binder pipeline...")
    >>> asyncio.run(p.complete("some-model", "", "design a binder", 0.7, 512))
    'Here is the binder pipeline...'
    """

    def __init__(self, response: str = "Mock response.") -> None:
        self._response = response

    async def complete(
        self,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Return the preset response, ignoring all parameters."""
        return self._response
