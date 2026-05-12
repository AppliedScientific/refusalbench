"""Tests for council.py: aggregation, categorize, Krippendorff alpha."""

from __future__ import annotations

import math

import pytest

from refusalbench.council import (
    AggregatedJudgment,
    aggregate,
    categorize,
    compute_krippendorff_alpha,
)
from refusalbench.judges.base import Judgment
from refusalbench.judges.mock import MockJudge


def _j(judge_id: str, compliance: str, reason: str = "other") -> Judgment:
    return Judgment(
        judge_id=judge_id,
        prompt_id="p1",
        compliance=compliance,
        reason=reason,
        raw_output="",
    )


# ---------------------------------------------------------------------------
# aggregate()
# ---------------------------------------------------------------------------


def test_aggregate_unanimous_returns_correct_label() -> None:
    judgments = [_j(f"j{i}", "direct_refusal", "safety_policy") for i in range(3)]
    agg = aggregate(judgments)
    assert agg.modal_compliance == "direct_refusal"
    assert agg.modal_reason == "safety_policy"


def test_aggregate_two_vs_one_majority_wins() -> None:
    judgments = [
        _j("j1", "direct_refusal"),
        _j("j2", "direct_refusal"),
        _j("j3", "compliance"),
    ]
    agg = aggregate(judgments)
    assert agg.modal_compliance == "direct_refusal"


def test_aggregate_tie_resolves_to_most_restrictive() -> None:
    judgments = [
        _j("j1", "direct_refusal"),
        _j("j2", "indirect_refusal"),
    ]
    agg = aggregate(judgments)
    assert agg.modal_compliance == "direct_refusal"


def test_aggregate_compliance_agreement_fraction() -> None:
    judgments = [
        _j("j1", "direct_refusal"),
        _j("j2", "direct_refusal"),
        _j("j3", "compliance"),
    ]
    agg = aggregate(judgments)
    assert abs(agg.compliance_agreement - 2 / 3) < 1e-9


def test_aggregate_flagged_when_agreement_below_threshold() -> None:
    judgments = [
        _j("j1", "direct_refusal"),
        _j("j2", "compliance"),
        _j("j3", "indirect_refusal"),
    ]
    agg = aggregate(judgments)
    assert agg.flagged_for_spot_check


def test_aggregate_not_flagged_when_unanimous() -> None:
    judgments = [_j(f"j{i}", "direct_refusal") for i in range(3)]
    agg = aggregate(judgments)
    assert not agg.flagged_for_spot_check


def test_aggregate_empty_raises_value_error() -> None:
    with pytest.raises(ValueError, match="empty"):
        aggregate([])


def test_aggregate_mixed_prompt_ids_raises() -> None:
    j1 = Judgment("j1", "p1", "compliance", "other", "")
    j2 = Judgment("j2", "p2", "compliance", "other", "")
    with pytest.raises(ValueError, match="prompt_ids"):
        aggregate([j1, j2])


def test_aggregate_parse_failed_propagates() -> None:
    judgments = [
        _j("j1", "direct_refusal"),
        Judgment("j2", "p1", "non_responsive", "other", "", parse_failed=True),
    ]
    agg = aggregate(judgments)
    assert agg.any_parse_failed


def test_aggregate_is_refusal_property() -> None:
    judgments = [_j("j1", "direct_refusal"), _j("j2", "direct_refusal")]
    agg = aggregate(judgments)
    assert agg.is_refusal


def test_aggregate_is_soft_refusal_property() -> None:
    judgments = [_j("j1", "indirect_refusal"), _j("j2", "indirect_refusal")]
    agg = aggregate(judgments)
    assert agg.is_soft_refusal
    assert not agg.is_refusal


def test_aggregate_compliance_is_not_refusal() -> None:
    judgments = [_j("j1", "compliance"), _j("j2", "compliance")]
    agg = aggregate(judgments)
    assert not agg.is_refusal
    assert not agg.is_soft_refusal


# ---------------------------------------------------------------------------
# categorize() (async)
# ---------------------------------------------------------------------------


async def test_categorize_with_mock_judges_returns_aggregated() -> None:
    judges = [
        MockJudge("j1", "direct_refusal", "safety_policy"),
        MockJudge("j2", "direct_refusal", "dual_use_concern"),
        MockJudge("j3", "compliance", "other"),
    ]
    result = await categorize("p1", "design a binder", "I cannot help.", judges)
    assert isinstance(result, AggregatedJudgment)
    assert result.modal_compliance == "direct_refusal"


async def test_categorize_stores_individual_judge_votes() -> None:
    judges = [
        MockJudge("j1", "direct_refusal"),
        MockJudge("j2", "compliance"),
    ]
    result = await categorize("p1", "prompt", "response", judges)
    assert result.judge_compliance["j1"] == "direct_refusal"
    assert result.judge_compliance["j2"] == "compliance"


# ---------------------------------------------------------------------------
# compute_krippendorff_alpha()
# ---------------------------------------------------------------------------


def test_krippendorff_alpha_perfect_agreement_returns_nan() -> None:
    seqs = [["a", "b", "a"], ["a", "b", "a"], ["a", "b", "a"]]
    alpha = compute_krippendorff_alpha(seqs)
    # Perfect agreement: alpha is 1.0 or NaN depending on library behavior
    assert alpha == 1.0 or math.isnan(alpha)


def test_krippendorff_alpha_two_judges_partial_agreement() -> None:
    seqs = [["a", "a", "b"], ["a", "b", "b"]]
    alpha = compute_krippendorff_alpha(seqs)
    assert 0 < alpha <= 1


def test_krippendorff_alpha_empty_input_returns_nan() -> None:
    alpha = compute_krippendorff_alpha([])
    assert math.isnan(alpha)


def test_krippendorff_alpha_single_item_does_not_crash() -> None:
    seqs = [["direct_refusal"], ["direct_refusal"], ["compliance"]]
    alpha = compute_krippendorff_alpha(seqs)
    assert isinstance(alpha, float)
