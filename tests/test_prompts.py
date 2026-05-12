"""Tests for prompt loading, validation, and paired-set logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from refusalbench.prompts import (
    PromptValidationError,
    Subdomain,
    Tier,
    is_frozen,
    load_paired_sets,
    load_prompts,
)

# ---------------------------------------------------------------------------
# Enum smoke tests
# ---------------------------------------------------------------------------


def test_subdomain_enum_has_eight_values() -> None:
    assert len(Subdomain) == 8


def test_tier_enum_has_three_values() -> None:
    assert len(Tier) == 3


def test_subdomain_binder_design_value() -> None:
    assert Subdomain.BINDER_DESIGN.value == "binder_design"


def test_tier_dual_use_value() -> None:
    assert Tier.DUAL_USE.value == "dual_use"


def test_all_control_subdomains_present() -> None:
    controls = {Subdomain.BIOINFORMATICS_SCRIPTING, Subdomain.PROTOCOL_DESIGN}
    assert controls.issubset(set(Subdomain))


# ---------------------------------------------------------------------------
# Loader with valid fixture
# ---------------------------------------------------------------------------


def test_load_prompts_returns_three_items(tmp_prompts: Path) -> None:
    prompts = load_prompts("1.0", tmp_prompts)
    assert len(prompts) == 3


def test_load_prompts_sorted_deterministically(tmp_prompts: Path) -> None:
    a = load_prompts("1.0", tmp_prompts)
    b = load_prompts("1.0", tmp_prompts)
    assert [p.prompt_id for p in a] == [p.prompt_id for p in b]


def test_load_prompts_prompt_fields_populated(tmp_prompts: Path) -> None:
    prompts = load_prompts("1.0", tmp_prompts)
    for p in prompts:
        assert p.prompt
        assert p.source_citation
        assert p.language == "en"


def test_load_prompts_subdomain_is_enum(tmp_prompts: Path) -> None:
    prompts = load_prompts("1.0", tmp_prompts)
    for p in prompts:
        assert isinstance(p.subdomain, Subdomain)


def test_load_prompts_tier_matches_directory(tmp_prompts: Path) -> None:
    prompts = load_prompts("1.0", tmp_prompts)
    by_tier = {p.tier for p in prompts}
    assert by_tier == {Tier.BENIGN, Tier.BORDERLINE, Tier.DUAL_USE}


def test_load_paired_sets_returns_one_triple(tmp_prompts: Path) -> None:
    sets = load_paired_sets("1.0", tmp_prompts)
    assert len(sets) == 1
    assert sets[0][0].tier == Tier.BENIGN
    assert sets[0][1].tier == Tier.BORDERLINE
    assert sets[0][2].tier == Tier.DUAL_USE


def test_load_prompts_raises_for_missing_version(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_prompts("99.0", tmp_path)


# ---------------------------------------------------------------------------
# Schema validation errors
# ---------------------------------------------------------------------------


def _write_prompt(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data))


def test_missing_required_field_raises(tmp_path: Path) -> None:
    root = tmp_path / "prompts" / "v1.0" / "benign"
    root.mkdir(parents=True)
    _write_prompt(
        root / "bad.json",
        {
            "prompt_id": "x",
            "subdomain": "binder_design",
            # missing tier, paired_with, prompt, source_citation, language
        },
    )
    with pytest.raises(PromptValidationError, match="missing fields"):
        load_prompts("1.0", tmp_path / "prompts")


def test_invalid_subdomain_raises(tmp_path: Path) -> None:
    root = tmp_path / "prompts" / "v1.0" / "benign"
    root.mkdir(parents=True)
    _write_prompt(
        root / "bad.json",
        {
            "prompt_id": "x",
            "subdomain": "not_a_real_subdomain",
            "tier": "benign",
            "paired_with": [],
            "prompt": "test",
            "source_citation": "test",
            "language": "en",
        },
    )
    with pytest.raises(PromptValidationError, match="subdomain"):
        load_prompts("1.0", tmp_path / "prompts")


def test_tier_mismatch_raises(tmp_path: Path) -> None:
    root = tmp_path / "prompts" / "v1.0" / "benign"
    root.mkdir(parents=True)
    _write_prompt(
        root / "bad.json",
        {
            "prompt_id": "x",
            "subdomain": "binder_design",
            "tier": "borderline",  # in benign/ directory
            "paired_with": [],
            "prompt": "test",
            "source_citation": "test",
            "language": "en",
        },
    )
    with pytest.raises(PromptValidationError, match="tier"):
        load_prompts("1.0", tmp_path / "prompts")


def test_duplicate_id_raises(tmp_prompts: Path) -> None:
    dup = {
        "prompt_id": "test_001_benign",  # duplicate
        "subdomain": "binder_design",
        "tier": "benign",
        "paired_with": [],
        "prompt": "duplicate",
        "source_citation": "test",
        "language": "en",
    }
    (tmp_prompts / "v1.0" / "benign" / "dup.json").write_text(json.dumps(dup))
    with pytest.raises(PromptValidationError, match="duplicate"):
        load_prompts("1.0", tmp_prompts)


def test_unresolved_paired_with_raises(tmp_path: Path) -> None:
    root = tmp_path / "prompts" / "v1.0" / "benign"
    root.mkdir(parents=True)
    _write_prompt(
        root / "p.json",
        {
            "prompt_id": "p",
            "subdomain": "binder_design",
            "tier": "benign",
            "paired_with": ["nonexistent_id"],
            "prompt": "test",
            "source_citation": "test",
            "language": "en",
        },
    )
    with pytest.raises(PromptValidationError, match="unknown id"):
        load_prompts("1.0", tmp_path / "prompts")


# ---------------------------------------------------------------------------
# Frozen set
# ---------------------------------------------------------------------------


def test_is_frozen_returns_false_without_marker(tmp_prompts: Path) -> None:
    assert not is_frozen("1.0", tmp_prompts)


def test_is_frozen_returns_true_with_marker(tmp_prompts_frozen: Path) -> None:
    assert is_frozen("1.0", tmp_prompts_frozen)


def test_load_prompts_works_on_frozen_set(tmp_prompts_frozen: Path) -> None:
    prompts = load_prompts("1.0", tmp_prompts_frozen)
    assert len(prompts) == 3
