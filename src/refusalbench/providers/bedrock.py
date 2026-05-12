"""AWS Bedrock provider (Converse API) — uniform interface for all Bedrock models.

Covers Anthropic, Meta, Mistral, DeepSeek, Qwen, and GLM (Z.AI) via a single
boto3 bedrock-runtime client.  Sync boto3 calls are off-loaded to the default
thread-pool executor so the async sweep can use it without blocking the loop.

Credentials are resolved in this order:
  1. ``BEDROCK_API_KEY`` env var (Bedrock API key, ``ABSK...`` prefix) — uses
     direct REST call with ``x-api-key`` header; no boto3 credential chain.
  2. ``AWS_SECRET_ACCESS_KEY`` env var that starts with ``ABSK`` — same path.
  3. Standard boto3 credential chain (``AWS_ACCESS_KEY_ID`` + secret, profile,
     IAM role, etc.)

Bedrock API keys (launched 2025) are single-string credentials with the
``ABSK`` prefix.  They authenticate via ``x-api-key`` header on the Bedrock
REST endpoint and do not require ``AWS_ACCESS_KEY_ID``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from functools import partial
from typing import Any

from refusalbench.providers.base import Provider, ProviderError

_DEFAULT_REGION = "us-east-1"
_BEDROCK_REST_BASE = "https://bedrock-runtime.{region}.amazonaws.com"


def _is_bedrock_api_key(value: str) -> bool:
    return value.startswith("ABSK")


class BedrockProvider(Provider):
    """Calls any Bedrock-hosted model via the Converse API.

    The Converse API presents a uniform request/response structure across all
    providers on Bedrock (Anthropic, Meta, Mistral, DeepSeek, Qwen, Z.AI).
    Supply the Bedrock model ID (e.g. cross-region inference profile IDs like
    ``us.anthropic.claude-opus-4-7-20250514-v1:0``) as the ``model`` argument
    to :meth:`complete`.

    Parameters
    ----------
    region_name:
        AWS region for the bedrock-runtime client.  Defaults to the
        ``AWS_REGION`` environment variable, then ``us-east-1``.
    max_retries:
        Botocore adaptive retry count (only used in boto3 path).

    Example
    -------
    >>> provider = BedrockProvider()
    >>> provider  # doctest: +ELLIPSIS
    <refusalbench.providers.bedrock.BedrockProvider object at ...>
    """

    def __init__(
        self,
        region_name: str | None = None,
        max_retries: int = 3,
    ) -> None:
        self._region = region_name or os.environ.get("AWS_REGION", _DEFAULT_REGION)
        self._max_retries = max_retries
        # Detect Bedrock API key credential path
        api_key = os.environ.get("BEDROCK_API_KEY", "")
        if not api_key:
            secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
            if _is_bedrock_api_key(secret):
                api_key = secret
        self._api_key: str = api_key

    def _client(self) -> Any:
        """Return a boto3 bedrock-runtime client (IAM credential path only)."""
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise ProviderError("boto3 required: pip install 'refusalbench[providers]'") from exc
        cfg = Config(retries={"max_attempts": self._max_retries, "mode": "adaptive"})
        return boto3.client("bedrock-runtime", region_name=self._region, config=cfg)

    def _converse_rest(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system_list: list[dict[str, str]],
        inference_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Call Bedrock Converse REST endpoint with Bearer auth header.

        The model ID is passed verbatim — cross-region inference profile
        prefixes (``us.``, ``eu.``, ``ap.``) are required for newer Claude
        models and must not be stripped.
        """
        model_encoded = urllib.parse.quote(model, safe=":.")
        base = _BEDROCK_REST_BASE.format(region=self._region)
        url = f"{base}/model/{model_encoded}/converse"
        # Claude 4.x models have deprecated the temperature parameter.
        inference_config.pop("temperature", None)
        body: dict[str, Any] = {
            "messages": messages,
            "inferenceConfig": inference_config,
        }
        if system_list:
            body["system"] = system_list
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode(errors="replace")
            raise ProviderError(f"Bedrock REST {exc.code}: {body_text}") from exc

    async def complete(
        self,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call the Bedrock Converse API and return the text response.

        Uses the Bedrock API key REST path when ``BEDROCK_API_KEY`` or an
        ``ABSK``-prefixed ``AWS_SECRET_ACCESS_KEY`` is set; otherwise falls
        back to boto3 with the standard IAM credential chain.

        The sync call (boto3 or urllib) is executed in the thread-pool executor
        so it does not block the asyncio event loop.

        Parameters
        ----------
        model:
            Bedrock model ID, e.g. ``us.anthropic.claude-opus-4-7-20250514-v1:0``.
        system:
            System prompt text (may be empty for models that ignore it).
        user:
            User turn text.
        temperature:
            Sampling temperature.
        max_tokens:
            Maximum tokens to generate.

        Raises
        ------
        ProviderError
            On any API error after retries are exhausted.
        """
        messages: list[dict[str, Any]] = [{"role": "user", "content": [{"text": user}]}]
        system_list: list[dict[str, str]] = [{"text": system}] if system else []
        inference_config: dict[str, Any] = {
            "maxTokens": max_tokens,
            "temperature": temperature,
        }

        loop = asyncio.get_running_loop()

        if self._api_key:
            fn = partial(
                self._converse_rest,
                model,
                messages,
                system_list,
                inference_config,
            )
        else:
            client = self._client()
            fn = partial(
                client.converse,
                modelId=model,
                messages=messages,
                system=system_list,
                inferenceConfig=inference_config,
            )

        # Retry loop with non-blocking exponential backoff.
        # asyncio.sleep releases the event loop during the wait so other
        # coroutines can make progress — unlike time.sleep inside a thread,
        # which blocks a thread-pool slot for the duration of the backoff and
        # starves all other concurrent callers.
        _retry_status = frozenset({429, 500, 502, 503, 504})
        last_exc: Exception = ProviderError("no attempts made")
        for attempt in range(self._max_retries + 1):
            try:
                response: dict[str, Any] = await loop.run_in_executor(None, fn)
                stop_reason = response.get("stopReason", "")
                if stop_reason == "content_filtered":
                    return "[CONTENT_FILTERED]"
                content = response["output"]["message"]["content"]
                # DeepSeek R1 (and other reasoning models) prepend a
                # reasoningContent block before the text block — iterate to find
                # the first block that carries a "text" key rather than assuming
                # content[0] is always the text block.
                text_block = next((block["text"] for block in content if "text" in block), "")
                return str(text_block)
            except ProviderError as exc:
                # Extract HTTP status code from the error message to decide
                # whether to retry.  ProviderError messages start with
                # "Bedrock REST <code>: ...".
                status = 0
                msg = str(exc)
                if msg.startswith("Bedrock REST "):
                    with contextlib.suppress(IndexError, ValueError):
                        status = int(msg.split()[2].rstrip(":"))
                if status in _retry_status and attempt < self._max_retries:
                    backoff = 2.0**attempt  # 1s, 2s, 4s
                    await asyncio.sleep(backoff)
                    last_exc = exc
                    continue
                raise
            except Exception as exc:
                raise ProviderError(f"Bedrock Converse API error: {exc}") from exc
        raise last_exc
