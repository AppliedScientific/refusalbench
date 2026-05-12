"""Tests for judge base class, LLMJudge, mock judge, and JSON parsing."""

from __future__ import annotations

import pytest

from refusalbench.judges.base import Judge, Judgment
from refusalbench.judges.mock import MockJudge


def test_mock_judge_returns_judgment() -> None:
    j = MockJudge()
    assert j.judge_id == "mock_judge"


async def test_mock_judge_correct_compliance_and_reason() -> None:
    j = MockJudge("j1", "direct_refusal", "safety_policy")
    result = await j.judge("p1", "prompt text", "response text")
    assert result.compliance == "direct_refusal"
    assert result.reason == "safety_policy"
    assert result.judge_id == "j1"
    assert result.prompt_id == "p1"
    assert not result.parse_failed


async def test_mock_judge_default_compliance_is_compliance() -> None:
    j = MockJudge()
    result = await j.judge("p1", "prompt", "response")
    assert result.compliance == "compliance"


async def test_mock_judge_custom_judge_id() -> None:
    j = MockJudge(judge_id="custom_id")
    result = await j.judge("p1", "prompt", "response")
    assert result.judge_id == "custom_id"


def test_judgment_is_frozen_dataclass() -> None:
    j = Judgment("j1", "p1", "compliance", "other", "raw", False)
    with pytest.raises((AttributeError, TypeError)):
        j.compliance = "direct_refusal"  # type: ignore[misc]


def test_judgment_parse_failed_defaults_false() -> None:
    j = Judgment("j1", "p1", "compliance", "other", "")
    assert not j.parse_failed


async def test_multiple_mock_judges_independent() -> None:
    j1 = MockJudge("j1", "direct_refusal", "safety_policy")
    j2 = MockJudge("j2", "compliance", "other")
    r1 = await j1.judge("p1", "prompt", "response")
    r2 = await j2.judge("p1", "prompt", "response")
    assert r1.compliance != r2.compliance


def test_judge_is_abstract_cannot_instantiate() -> None:
    with pytest.raises(TypeError):
        Judge()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


def test_parse_json_label_valid_json() -> None:
    from refusalbench.judges.llm_judge import _parse_json_label

    compliance, reason, failed = _parse_json_label(
        '{"compliance": "direct_refusal", "reason": "safety_policy"}'
    )
    assert compliance == "direct_refusal"
    assert reason == "safety_policy"
    assert not failed


def test_parse_json_label_with_markdown_fences() -> None:
    from refusalbench.judges.llm_judge import _parse_json_label

    raw = '```json\n{"compliance": "compliance", "reason": "other"}\n```'
    compliance, _reason, failed = _parse_json_label(raw)
    assert compliance == "compliance"
    assert not failed


def test_parse_json_label_invalid_json_sets_parse_failed() -> None:
    from refusalbench.judges.llm_judge import _parse_json_label

    compliance, reason, failed = _parse_json_label("not json at all")
    assert failed
    assert compliance == "non_responsive"
    assert reason == "other"


def test_parse_json_label_empty_string_sets_parse_failed() -> None:
    from refusalbench.judges.llm_judge import _parse_json_label

    _compliance, _reason, failed = _parse_json_label("")
    assert failed


# ---------------------------------------------------------------------------
# LLMJudge tests (constructor-based, no __new__ bypassing)
# ---------------------------------------------------------------------------


async def test_llm_judge_id() -> None:
    from refusalbench.judges.llm_judge import LLMJudge
    from refusalbench.providers.mock import MockProvider

    judge = LLMJudge(
        judge_id="llama_guard_4",
        model_id="us.meta.llama-guard-4-12b-v1:0",
        provider=MockProvider('{"compliance": "direct_refusal", "reason": "safety_policy"}'),
    )
    assert judge.judge_id == "llama_guard_4"


async def test_llm_judge_returns_judgment() -> None:
    from refusalbench.judges.llm_judge import LLMJudge
    from refusalbench.providers.mock import MockProvider

    judge = LLMJudge(
        judge_id="llama_guard_4",
        model_id="us.meta.llama-guard-4-12b-v1:0",
        provider=MockProvider('{"compliance": "direct_refusal", "reason": "safety_policy"}'),
    )
    result = await judge.judge("p1", "protein binder prompt", "I cannot help with this.")
    assert result.compliance == "direct_refusal"
    assert result.reason == "safety_policy"
    assert not result.parse_failed
    assert result.judge_id == "llama_guard_4"


async def test_llm_judge_parse_failed_on_bad_output() -> None:
    from refusalbench.judges.llm_judge import LLMJudge
    from refusalbench.providers.mock import MockProvider

    judge = LLMJudge(
        judge_id="qwen3_32b",
        model_id="us.qwen.qwen3-32b-v1:0",
        provider=MockProvider("not valid json at all"),
    )
    result = await judge.judge("p1", "prompt", "response")
    assert result.parse_failed
    assert result.compliance == "non_responsive"


async def test_llm_judge_raises_judgment_error_on_provider_failure() -> None:
    from refusalbench.judges.base import JudgmentError
    from refusalbench.judges.llm_judge import LLMJudge
    from refusalbench.providers.base import ProviderError
    from refusalbench.providers.mock import MockProvider

    class FailingProvider(MockProvider):
        async def complete(
            self, model: str, system: str, user: str, temperature: float, max_tokens: int
        ) -> str:
            raise ProviderError("connection refused")

    judge = LLMJudge(
        judge_id="mistral_7b_judge",
        model_id="mistral.mistral-7b-instruct-v0:2",
        provider=FailingProvider(),
    )
    with pytest.raises(JudgmentError):
        await judge.judge("p1", "prompt", "response")


async def test_llm_judge_different_model_ids_independent() -> None:
    from refusalbench.judges.llm_judge import LLMJudge
    from refusalbench.providers.mock import MockProvider

    j1 = LLMJudge(
        judge_id="j1",
        model_id="model-a",
        provider=MockProvider('{"compliance": "direct_refusal", "reason": "safety_policy"}'),
    )
    j2 = LLMJudge(
        judge_id="j2",
        model_id="model-b",
        provider=MockProvider('{"compliance": "compliance", "reason": "other"}'),
    )
    r1 = await j1.judge("p1", "prompt", "response")
    r2 = await j2.judge("p1", "prompt", "response")
    assert r1.compliance == "direct_refusal"
    assert r2.compliance == "compliance"


# ---------------------------------------------------------------------------
# build_judges_from_config
# ---------------------------------------------------------------------------


def test_build_judges_from_config_returns_three_judges() -> None:
    from refusalbench.judges.llm_judge import build_judges_from_config
    from refusalbench.providers.mock import MockProvider

    judges = build_judges_from_config(
        provider_override=MockProvider('{"compliance": "compliance", "reason": "other"}')
    )
    assert len(judges) == 3


def test_build_judges_from_config_judge_ids_match_config() -> None:
    from refusalbench.judges.llm_judge import build_judges_from_config
    from refusalbench.providers.mock import MockProvider

    judges = build_judges_from_config(
        provider_override=MockProvider('{"compliance": "compliance", "reason": "other"}')
    )
    ids = [j.judge_id for j in judges]
    assert "nvidia_nemotron" in ids
    assert "cohere_command_r_plus" in ids
    assert "ai21_jamba" in ids


async def test_build_judges_from_config_judges_produce_judgments() -> None:
    from refusalbench.judges.llm_judge import build_judges_from_config
    from refusalbench.providers.mock import MockProvider

    judges = build_judges_from_config(
        provider_override=MockProvider('{"compliance": "compliance", "reason": "other"}')
    )
    for judge in judges:
        result = await judge.judge("p1", "prompt text", "response text")
        assert result.compliance == "compliance"
        assert not result.parse_failed
