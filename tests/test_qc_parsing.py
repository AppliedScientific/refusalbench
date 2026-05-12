"""Tests for the optional QC council parsing and aggregation."""

from __future__ import annotations

import pytest

from refusalbench.prompt_build.qc_council import (
    AggregatedQCScore,
    QCJudgment,
    aggregate_qc_judgments,
    parse_qc_response,
)


def _make_judgment(
    judge_id: str = "j1",
    prompt_id: str = "p1",
    naturalness: str = "yes",
    leakage: str = "low",
    artifact: str = "low",
    plausibility: str = "yes",
    sensitivity: str = "aligned",
    parse_failed: bool = False,
) -> QCJudgment:
    return QCJudgment(
        judge_id=judge_id,
        prompt_id=prompt_id,
        q1_naturalness=naturalness,
        q2_tier_leakage=leakage,
        q3_template_artifact=artifact,
        q4_scientific_plausibility=plausibility,
        q5_sensitivity_mismatch=sensitivity,
        parse_failed=parse_failed,
    )


# ---------------------------------------------------------------------------
# parse_qc_response
# ---------------------------------------------------------------------------


def test_parse_valid_json_response() -> None:
    raw = (
        '{"q1_naturalness": "yes", "q2_tier_leakage": "low", '
        '"q3_template_artifact": "low", "q4_scientific_plausibility": "yes", '
        '"q5_sensitivity_mismatch": "aligned"}'
    )
    j = parse_qc_response(raw, "judge_1", "prompt_1")
    assert j.q1_naturalness == "yes"
    assert j.q2_tier_leakage == "low"
    assert not j.parse_failed
    assert j.judge_id == "judge_1"
    assert j.prompt_id == "prompt_1"


def test_parse_json_with_markdown_fences() -> None:
    inner = (
        '{"q1_naturalness": "borderline", "q2_tier_leakage": "medium",'
        ' "q3_template_artifact": "low", "q4_scientific_plausibility": "uncertain",'
        ' "q5_sensitivity_mismatch": "possibly_mismatched"}'
    )
    raw = f"```json\n{inner}\n```"
    j = parse_qc_response(raw, "j", "p")
    assert j.q1_naturalness == "borderline"
    assert not j.parse_failed


def test_parse_invalid_json_sets_parse_failed() -> None:
    j = parse_qc_response("not valid json", "j", "p")
    assert j.parse_failed


def test_parse_empty_response_sets_parse_failed() -> None:
    j = parse_qc_response("", "j", "p")
    assert j.parse_failed


def test_parse_with_rationale_field() -> None:
    raw = (
        '{"q1_naturalness": "yes", "q2_tier_leakage": "low", '
        '"q3_template_artifact": "low", "q4_scientific_plausibility": "yes", '
        '"q5_sensitivity_mismatch": "aligned", '
        '"rationale": {"q1": "reads naturally", "q4": "consistent subdomain"}}'
    )
    j = parse_qc_response(raw, "j", "p")
    assert j.rationale.get("q1") == "reads naturally"


# ---------------------------------------------------------------------------
# aggregate_qc_judgments
# ---------------------------------------------------------------------------


def test_aggregate_all_positive_not_flagged() -> None:
    judgments = [_make_judgment(judge_id=f"j{i}") for i in range(3)]
    result = aggregate_qc_judgments(judgments, {})
    assert not result.flagged
    assert result.modal_naturalness == "yes"
    assert result.disagreement_score == 0.0


def test_aggregate_majority_naturalness_no_triggers_flag() -> None:
    judgments = [
        _make_judgment("j1", naturalness="no"),
        _make_judgment("j2", naturalness="no"),
        _make_judgment("j3", naturalness="yes"),
    ]
    result = aggregate_qc_judgments(judgments, {"flag_if_majority_naturalness_no": True})
    assert result.flagged
    assert "majority_naturalness_no" in result.flag_reasons


def test_aggregate_majority_tier_leakage_high_triggers_flag() -> None:
    judgments = [
        _make_judgment("j1", leakage="high"),
        _make_judgment("j2", leakage="high"),
        _make_judgment("j3", leakage="low"),
    ]
    result = aggregate_qc_judgments(judgments, {"flag_if_majority_tier_leakage_high": True})
    assert result.flagged
    assert "majority_tier_leakage_high" in result.flag_reasons


def test_aggregate_disagreement_score_triggers_flag() -> None:
    judgments = [
        _make_judgment("j1", naturalness="yes", leakage="high"),
        _make_judgment("j2", naturalness="no", leakage="low"),
    ]
    result = aggregate_qc_judgments(judgments, {"flag_if_disagreement_exceeds": 0.1})
    assert result.flagged


def test_aggregate_no_flags_with_empty_rules() -> None:
    judgments = [
        _make_judgment("j1", naturalness="no"),
        _make_judgment("j2", naturalness="no"),
    ]
    result = aggregate_qc_judgments(judgments, {})
    assert not result.flagged


def test_aggregate_raises_on_empty_judgments() -> None:
    from refusalbench.prompt_build.qc_council import QCError

    with pytest.raises(QCError):
        aggregate_qc_judgments([], {})


def test_aggregate_parse_failed_judgments_excluded() -> None:
    judgments = [
        _make_judgment("j1", naturalness="no", parse_failed=True),
        _make_judgment("j2", naturalness="no", parse_failed=True),
        _make_judgment("j3", naturalness="yes"),
    ]
    result = aggregate_qc_judgments(judgments, {"flag_if_majority_naturalness_no": True})
    # Only j3 counted → not majority "no"
    assert not result.flagged or result.modal_naturalness == "yes"


def test_aggregate_judge_count() -> None:
    judgments = [_make_judgment(f"j{i}") for i in range(3)]
    result = aggregate_qc_judgments(judgments, {})
    assert result.judge_count == 3


# ---------------------------------------------------------------------------
# write_qc_outputs
# ---------------------------------------------------------------------------


def test_write_qc_outputs_creates_files(tmp_path: pytest.TempPathFixture) -> None:  # type: ignore[name-defined]
    from refusalbench.prompt_build.qc_council import write_qc_outputs

    scores = [
        AggregatedQCScore(
            prompt_id="p1",
            modal_naturalness="yes",
            modal_tier_leakage="low",
            modal_template_artifact="low",
            modal_plausibility="yes",
            modal_sensitivity_mismatch="aligned",
            flagged=False,
            flag_reasons=[],
            disagreement_score=0.0,
            judge_count=2,
        )
    ]
    raw_judgments = [_make_judgment()]
    write_qc_outputs(scores, raw_judgments, tmp_path)

    assert (tmp_path / "raw_judgments.jsonl").exists()
    assert (tmp_path / "aggregated_scores.csv").exists()
    assert (tmp_path / "flagged_prompts.csv").exists()
    assert (tmp_path / "disagreement_summary.csv").exists()
    assert (tmp_path / "qc_readme.md").exists()
