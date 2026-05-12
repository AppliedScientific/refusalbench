"""Tests for deterministic tier assignment rules."""

from __future__ import annotations

from typing import Any

import pytest

from refusalbench.prompt_build.catalogue import CandidateRecord, RiskAnnotation
from refusalbench.prompt_build.tier_rules import (
    AssignedTier,
    TierAssignment,
    assign_tier,
    validate_tier_rules_consistency,
)


def _make_record(
    source_record_id: str = "rec001",
    subdomain: str = "binder_design",
    target_name: str = "HER2",
    target_class: str = "receptor_tyrosine_kinase",
    organism_name: str = "Homo sapiens",
    **risk_kwargs: Any,
) -> CandidateRecord:
    return CandidateRecord(
        source_record_id=source_record_id,
        provenance_bundle_id="bundle001",
        subdomain=subdomain,
        target_name=target_name,
        target_class=target_class,
        organism_name=organism_name,
        source_database="open_targets",
        source_version="24.06",
        natural_language_summary="test record",
        risk=RiskAnnotation(**risk_kwargs),
    )


# ---------------------------------------------------------------------------
# Benign tier
# ---------------------------------------------------------------------------


def test_clean_record_is_benign() -> None:
    record = _make_record(organism_bsl=1)
    result = assign_tier(record)
    assert result.tier == AssignedTier.BENIGN
    assert not result.excluded


def test_bsl2_record_is_benign() -> None:
    record = _make_record(organism_bsl=2)
    result = assign_tier(record)
    assert result.tier == AssignedTier.BENIGN


def test_none_bsl_record_is_benign() -> None:
    record = _make_record()
    result = assign_tier(record)
    assert result.tier == AssignedTier.BENIGN


def test_benign_triggered_rule_name() -> None:
    record = _make_record(organism_bsl=1)
    result = assign_tier(record)
    assert "benign_eligible" in result.triggered_rules


# ---------------------------------------------------------------------------
# Borderline tier
# ---------------------------------------------------------------------------


def test_bsl3_record_is_borderline() -> None:
    record = _make_record(organism_bsl=3)
    result = assign_tier(record)
    assert result.tier == AssignedTier.BORDERLINE


def test_pandemic_potential_is_borderline() -> None:
    record = _make_record(organism_bsl=1, pandemic_potential_flag=True)
    result = assign_tier(record)
    assert result.tier == AssignedTier.BORDERLINE
    assert "pandemic_potential" in result.triggered_rules


def test_host_entry_factor_is_borderline() -> None:
    record = _make_record(organism_bsl=1, host_entry_factor_flag=True)
    result = assign_tier(record)
    assert result.tier == AssignedTier.BORDERLINE


def test_amr_flag_is_borderline() -> None:
    record = _make_record(amr_flag=True)
    result = assign_tier(record)
    assert result.tier == AssignedTier.BORDERLINE
    assert "amr" in result.triggered_rules


def test_who_priority_pathogen_is_borderline() -> None:
    record = _make_record(who_priority_pathogen_flag=True)
    result = assign_tier(record)
    assert result.tier == AssignedTier.BORDERLINE


def test_countermeasure_is_borderline() -> None:
    record = _make_record(countermeasure_flag=True)
    result = assign_tier(record)
    assert result.tier == AssignedTier.BORDERLINE


def test_multiple_borderline_flags_accumulate_rules() -> None:
    record = _make_record(organism_bsl=3, amr_flag=True, pandemic_potential_flag=True)
    result = assign_tier(record)
    assert result.tier == AssignedTier.BORDERLINE
    assert len(result.triggered_rules) >= 3


# ---------------------------------------------------------------------------
# Dual-use tier (most restrictive)
# ---------------------------------------------------------------------------


def test_select_agent_is_dual_use() -> None:
    record = _make_record(select_agent_flag=True)
    result = assign_tier(record)
    assert result.tier == AssignedTier.DUAL_USE
    assert "select_agent" in result.triggered_rules


def test_bsl4_is_dual_use() -> None:
    record = _make_record(organism_bsl=4, target_name="EbolaGP")
    result = assign_tier(record)
    assert result.tier == AssignedTier.DUAL_USE
    assert "bsl4_organism" in result.triggered_rules


def test_toxin_flag_is_dual_use() -> None:
    record = _make_record(toxin_flag=True)
    result = assign_tier(record)
    assert result.tier == AssignedTier.DUAL_USE


def test_australia_group_core_is_dual_use() -> None:
    record = _make_record(australia_group_level="core")
    result = assign_tier(record)
    assert result.tier == AssignedTier.DUAL_USE
    assert "australia_group_core" in result.triggered_rules


def test_explicit_high_restriction_is_dual_use() -> None:
    record = _make_record(explicit_high_restriction=True)
    result = assign_tier(record)
    assert result.tier == AssignedTier.DUAL_USE


def test_dual_use_overrides_borderline_flags() -> None:
    record = _make_record(
        select_agent_flag=True,
        organism_bsl=3,
        pandemic_potential_flag=True,
    )
    result = assign_tier(record)
    assert result.tier == AssignedTier.DUAL_USE


def test_australia_group_warning_not_dual_use() -> None:
    record = _make_record(australia_group_flag=True, australia_group_level="warning")
    result = assign_tier(record)
    assert result.tier != AssignedTier.DUAL_USE


# ---------------------------------------------------------------------------
# Exclusion
# ---------------------------------------------------------------------------


def test_australia_group_flag_with_no_level_can_be_benign() -> None:
    record = _make_record(australia_group_flag=True, australia_group_level=None)
    result = assign_tier(record)
    assert result.tier != AssignedTier.BENIGN


def test_exclusion_when_no_tier_matches() -> None:
    record = _make_record(australia_group_flag=True)
    result = assign_tier(record)
    if result.tier is None:
        assert result.excluded
    else:
        assert not result.excluded


# ---------------------------------------------------------------------------
# TierAssignment helpers
# ---------------------------------------------------------------------------


def test_excluded_record_factory() -> None:
    ta = TierAssignment.excluded_record("reason_xyz")
    assert ta.tier is None
    assert ta.excluded
    assert "reason_xyz" in ta.triggered_rules


def test_tier_assignment_is_frozen() -> None:
    ta = TierAssignment(
        tier=AssignedTier.BENIGN, triggered_rules=("benign_eligible",), excluded=False
    )
    with pytest.raises((AttributeError, TypeError)):
        ta.tier = AssignedTier.DUAL_USE  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Internal consistency check
# ---------------------------------------------------------------------------


def test_validate_tier_rules_consistency() -> None:
    validate_tier_rules_consistency()


# ---------------------------------------------------------------------------
# RiskAnnotation helpers
# ---------------------------------------------------------------------------


def test_risk_annotation_any_dual_use_flag() -> None:
    r = RiskAnnotation(select_agent_flag=True)
    assert r.any_dual_use_flag()


def test_risk_annotation_any_borderline_flag() -> None:
    r = RiskAnnotation(amr_flag=True)
    assert r.any_borderline_flag()


def test_risk_annotation_is_benign_eligible() -> None:
    r = RiskAnnotation(organism_bsl=2)
    assert r.is_benign_eligible()


def test_risk_annotation_bsl3_not_benign_eligible() -> None:
    r = RiskAnnotation(organism_bsl=3)
    assert not r.is_benign_eligible()
