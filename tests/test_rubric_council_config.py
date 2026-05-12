"""Tests for benchmark/rubric.json and benchmark/council/v1.1.json loading and consistency."""

from __future__ import annotations

import json
from pathlib import Path

from refusalbench.council import (
    COMPLIANCE_KEYS,
    REASON_KEYS,
    REFUSAL_KEYS,
    SOFT_REFUSAL_KEYS,
    load_council_config,
    load_rubric,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_rubric_loads_without_error() -> None:
    rubric = load_rubric()
    assert "compliance_levels" in rubric
    assert "reason_categories" in rubric


def test_rubric_has_five_compliance_levels() -> None:
    rubric = load_rubric()
    assert len(rubric["compliance_levels"]) == 5


def test_rubric_has_sixteen_reason_categories() -> None:
    rubric = load_rubric()
    assert len(rubric["reason_categories"]) == 16


def test_rubric_compliance_keys_match_module_constants() -> None:
    rubric = load_rubric()
    json_keys = {level["key"] for level in rubric["compliance_levels"]}
    assert json_keys == COMPLIANCE_KEYS


def test_rubric_reason_keys_match_module_constants() -> None:
    rubric = load_rubric()
    json_keys = {cat["key"] for cat in rubric["reason_categories"]}
    assert json_keys == REASON_KEYS


def test_refusal_keys_are_subset_of_compliance_keys() -> None:
    assert REFUSAL_KEYS.issubset(COMPLIANCE_KEYS)


def test_soft_refusal_keys_are_subset_of_compliance_keys() -> None:
    assert SOFT_REFUSAL_KEYS.issubset(COMPLIANCE_KEYS)


def test_refusal_and_soft_refusal_disjoint() -> None:
    assert REFUSAL_KEYS.isdisjoint(SOFT_REFUSAL_KEYS)


def test_direct_refusal_in_refusal_keys() -> None:
    assert "direct_refusal" in REFUSAL_KEYS


def test_non_responsive_in_refusal_keys() -> None:
    assert "non_responsive" in REFUSAL_KEYS


def test_compliance_not_in_refusal_keys() -> None:
    assert "compliance" not in REFUSAL_KEYS


def test_rubric_decision_rules_present() -> None:
    rubric = load_rubric()
    assert len(rubric.get("decision_rules", [])) >= 3


def test_rubric_examples_present() -> None:
    rubric = load_rubric()
    assert len(rubric.get("examples", [])) >= 3


def test_council_config_loads_without_error() -> None:
    cfg = load_council_config()
    assert "judges" in cfg


def test_council_config_has_three_judges() -> None:
    cfg = load_council_config()
    assert len(cfg["judges"]) == 3


def test_council_judge_ids_unique() -> None:
    cfg = load_council_config()
    ids = [j["judge_id"] for j in cfg["judges"]]
    assert len(ids) == len(set(ids))


def test_council_judges_span_three_distinct_jurisdictions() -> None:
    cfg = load_council_config()
    jurisdictions = {j["jurisdiction"] for j in cfg["judges"]}
    assert len(jurisdictions) == 3, f"Expected 3 distinct jurisdictions, got: {jurisdictions}"


def test_council_judge_required_fields() -> None:
    cfg = load_council_config()
    required = {"judge_id", "provider", "model_id", "temperature", "max_tokens"}
    for judge in cfg["judges"]:
        missing = required - set(judge.keys())
        assert not missing, f"Judge {judge.get('judge_id')} missing: {missing}"


def test_rubric_file_is_valid_json() -> None:
    path = _REPO_ROOT / "benchmark" / "rubric.json"
    with path.open() as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_council_file_is_valid_json() -> None:
    path = _REPO_ROOT / "benchmark" / "council" / "v1.1.json"
    with path.open() as f:
        data = json.load(f)
    assert isinstance(data, dict)
