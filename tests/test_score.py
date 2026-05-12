"""Tests for score.py: refusal rates, bootstrap CIs, group aggregation."""

from __future__ import annotations

import math

import pandas as pd

from refusalbench.score import (
    bootstrap_ci,
    compute_refusal_rate,
    inter_judge_agreement,
    refusal_rates_by_group,
    tier_comparison,
)

# ---------------------------------------------------------------------------
# compute_refusal_rate
# ---------------------------------------------------------------------------


def test_refusal_rate_all_refusals() -> None:
    records = [{"modal_compliance": "direct_refusal"}] * 4
    assert compute_refusal_rate(records) == 1.0


def test_refusal_rate_no_refusals() -> None:
    records = [{"modal_compliance": "compliance"}] * 4
    assert compute_refusal_rate(records) == 0.0


def test_refusal_rate_partial_strict() -> None:
    records = [
        {"modal_compliance": "direct_refusal"},
        {"modal_compliance": "compliance"},
        {"modal_compliance": "indirect_refusal"},  # soft — not counted strictly
    ]
    rate = compute_refusal_rate(records, strict=True)
    assert abs(rate - 1 / 3) < 1e-9


def test_refusal_rate_partial_lenient() -> None:
    records = [
        {"modal_compliance": "direct_refusal"},
        {"modal_compliance": "compliance"},
        {"modal_compliance": "indirect_refusal"},
    ]
    rate = compute_refusal_rate(records, strict=False)
    assert abs(rate - 2 / 3) < 1e-9


def test_refusal_rate_empty_returns_nan() -> None:
    assert math.isnan(compute_refusal_rate([]))


def test_refusal_rate_non_responsive_counts_as_refusal() -> None:
    records = [{"modal_compliance": "non_responsive"}]
    assert compute_refusal_rate(records) == 1.0


# ---------------------------------------------------------------------------
# bootstrap_ci
# ---------------------------------------------------------------------------


def test_bootstrap_ci_all_ones() -> None:
    mean, lo, hi = bootstrap_ci([1.0] * 10, seed=0)
    assert mean == 1.0
    assert lo == 1.0
    assert hi == 1.0


def test_bootstrap_ci_all_zeros() -> None:
    mean, _lo, _hi = bootstrap_ci([0.0] * 10, seed=0)
    assert mean == 0.0


def test_bootstrap_ci_mean_within_interval() -> None:
    values = [1, 0, 1, 1, 0, 1, 0, 0]
    mean, lo, hi = bootstrap_ci(values, seed=42)
    assert lo <= mean <= hi


def test_bootstrap_ci_empty_returns_nan() -> None:
    mean, _lo, _hi = bootstrap_ci([], seed=0)
    assert math.isnan(mean)


def test_bootstrap_ci_single_value() -> None:
    mean, lo, hi = bootstrap_ci([0.5], seed=0)
    assert mean == 0.5
    assert lo == hi == 0.5


def test_bootstrap_ci_reproducible_with_same_seed() -> None:
    a = bootstrap_ci([1, 0, 1, 0, 1], seed=99)
    b = bootstrap_ci([1, 0, 1, 0, 1], seed=99)
    assert a == b


# ---------------------------------------------------------------------------
# refusal_rates_by_group
# ---------------------------------------------------------------------------


def _make_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "model": ["opus", "opus", "mistral", "mistral"],
            "modal_compliance": ["direct_refusal", "compliance", "compliance", "compliance"],
        }
    )


def test_refusal_rates_by_group_schema() -> None:
    df = _make_df()
    out = refusal_rates_by_group(df, ["model"])
    assert set(out.columns) >= {"model", "refusal_rate", "ci_lo", "ci_hi", "n"}


def test_refusal_rates_by_group_values() -> None:
    df = _make_df()
    out = refusal_rates_by_group(df, ["model"]).set_index("model")
    assert out.loc["opus", "refusal_rate"] == 0.5
    assert out.loc["mistral", "refusal_rate"] == 0.0


# ---------------------------------------------------------------------------
# inter_judge_agreement
# ---------------------------------------------------------------------------


def test_inter_judge_agreement_returns_alpha() -> None:
    df = pd.DataFrame(
        {
            "judge_id": ["j1", "j2", "j3", "j1", "j2", "j3"],
            "prompt_id": ["p1", "p1", "p1", "p2", "p2", "p2"],
            "compliance": [
                "direct_refusal",
                "direct_refusal",
                "compliance",
                "compliance",
                "compliance",
                "compliance",
            ],
        }
    )
    result = inter_judge_agreement(df)
    assert "alpha" in result
    assert "n_items" in result
    assert result["n_items"] == 2


def test_inter_judge_agreement_perfect_returns_nan_or_one() -> None:
    df = pd.DataFrame(
        {
            "judge_id": ["j1", "j2"] * 3,
            "prompt_id": ["p1", "p1", "p2", "p2", "p3", "p3"],
            "compliance": ["direct_refusal"] * 6,
        }
    )
    result = inter_judge_agreement(df)
    assert math.isnan(result["alpha"]) or abs(result["alpha"] - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# tier_comparison
# ---------------------------------------------------------------------------


def test_tier_comparison_returns_tier_column() -> None:
    df = pd.DataFrame(
        {
            "model": ["opus"] * 3,
            "tier": ["benign", "borderline", "dual_use"],
            "modal_compliance": ["direct_refusal", "direct_refusal", "direct_refusal"],
        }
    )
    out = tier_comparison(df)
    assert "tier" in out.columns
    assert len(out) == 3
