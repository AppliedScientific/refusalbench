"""Tests for provider adapters (mock provider; real providers tested at integration level)."""

from __future__ import annotations

import pytest

from refusalbench.providers.base import Provider, ProviderError
from refusalbench.providers.mock import MockProvider


async def test_mock_provider_returns_preset_response() -> None:
    p = MockProvider("hello world")
    result = await p.complete("model", "system", "user", 0.7, 512)
    assert result == "hello world"


async def test_mock_provider_default_response() -> None:
    p = MockProvider()
    result = await p.complete("model", "system", "user", 0.0, 128)
    assert result == "Mock response."


async def test_mock_provider_ignores_model_parameter() -> None:
    p = MockProvider("fixed")
    r1 = await p.complete("model-a", "", "", 0.0, 1)
    r2 = await p.complete("model-b", "", "", 0.0, 1)
    assert r1 == r2 == "fixed"


def test_provider_is_abstract_cannot_instantiate() -> None:
    with pytest.raises(TypeError):
        Provider()  # type: ignore[abstract]


def test_openrouter_provider_raises_provider_error_without_config() -> None:
    from refusalbench.providers.openrouter import OpenRouterProvider

    p = OpenRouterProvider(api_key="")
    # Raises ProviderError for either missing package or missing key
    with pytest.raises(ProviderError):
        p._client()


def test_anthropic_provider_raises_provider_error_without_config() -> None:
    from refusalbench.providers.anthropic import AnthropicProvider

    p = AnthropicProvider(api_key="")
    with pytest.raises(ProviderError):
        p._client()


def test_bedrock_provider_instantiates_with_defaults() -> None:
    from refusalbench.providers.bedrock import BedrockProvider

    p = BedrockProvider()
    assert p._region == "us-east-1"


def test_bedrock_provider_respects_region_override() -> None:
    from refusalbench.providers.bedrock import BedrockProvider

    p = BedrockProvider(region_name="eu-west-1")
    assert p._region == "eu-west-1"


def test_bedrock_provider_raises_provider_error_without_boto3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    from refusalbench.providers.bedrock import BedrockProvider

    p = BedrockProvider()
    boto3_backup = sys.modules.get("boto3")
    botocore_backup = sys.modules.get("botocore")
    botocore_config_backup = sys.modules.get("botocore.config")
    # Mask boto3 so the import inside _client() fails
    sys.modules["boto3"] = None  # type: ignore[assignment]
    sys.modules["botocore"] = None  # type: ignore[assignment]
    sys.modules["botocore.config"] = None  # type: ignore[assignment]
    try:
        with pytest.raises(ProviderError, match="boto3 required"):
            p._client()
    finally:
        if boto3_backup is None:
            del sys.modules["boto3"]
        else:
            sys.modules["boto3"] = boto3_backup
        if botocore_backup is None:
            del sys.modules["botocore"]
        else:
            sys.modules["botocore"] = botocore_backup
        if botocore_config_backup is None:
            del sys.modules["botocore.config"]
        else:
            sys.modules["botocore.config"] = botocore_config_backup


async def test_bedrock_provider_complete_wraps_exception_as_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bedrock complete() re-raises non-ProviderError exceptions as ProviderError."""
    from unittest.mock import MagicMock, patch

    from refusalbench.providers.bedrock import BedrockProvider

    p = BedrockProvider()
    failing_client = MagicMock()
    failing_client.converse.side_effect = RuntimeError("connection timeout")
    with (
        patch.object(p, "_client", return_value=failing_client),
        pytest.raises(ProviderError, match="Bedrock Converse API error"),
    ):
        await p.complete(
            "us.anthropic.claude-opus-4-7-20250514-v1:0",
            "system",
            "user text",
            0.7,
            512,
        )
