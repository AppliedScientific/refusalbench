"""Abstract provider base class for model API calls."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderError(RuntimeError):
    """Raised when a provider call fails after all retries."""


class Provider(ABC):
    """Abstract base for all model providers.

    Each provider wraps one underlying API (Anthropic, OpenRouter, etc.)
    and exposes a single async ``complete`` method. The runner calls
    providers directly; judges have their own provider instances.

    Example
    -------
    >>> class MyProvider(Provider):
    ...     async def complete(self, model, system, user, temperature, max_tokens):
    ...         return "mock response"
    """

    @abstractmethod
    async def complete(
        self,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call the model and return the response text.

        Parameters
        ----------
        model:
            Provider-specific model identifier.
        system:
            System prompt text.
        user:
            User turn text.
        temperature:
            Sampling temperature (0.0 for deterministic).
        max_tokens:
            Maximum response length.

        Returns
        -------
        str
            Response text from the model.

        Raises
        ------
        ProviderError
            On hard failures after all retries.
        """
