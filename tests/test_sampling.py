"""Tests for provenance_bundle_id-based triple pairing in sampling.py."""

from __future__ import annotations

from refusalbench.prompt_build.catalogue import CandidateRecord, RiskAnnotation
from refusalbench.prompt_build.sampling import sample_controls, sample_paired_sets
from refusalbench.prompt_build.tier_rules import AssignedTier, TierAssignment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ta(tier: AssignedTier) -> TierAssignment:
    return TierAssignment(tier=tier, triggered_rules=(tier.value,), excluded=False)


def _rec(
    *,
    subdomain: str = "binder_design",
    source_record_id: str = "rec001",
    provenance_bundle_id: str = "bundle001",
    bsl: int = 1,
    target_name: str = "HER2",
) -> CandidateRecord:
    return CandidateRecord(
        source_record_id=source_record_id,
        provenance_bundle_id=provenance_bundle_id,
        subdomain=subdomain,
        target_name=target_name,
        target_class="receptor",
        organism_name="Homo sapiens",
        source_database="open_targets",
        source_version="24.06",
        natural_language_summary="test",
        risk=RiskAnnotation(organism_bsl=bsl),
    )


def _assigned(
    records: list[CandidateRecord],
    tier: AssignedTier,
) -> list[tuple[CandidateRecord, TierAssignment]]:
    return [(r, _ta(tier)) for r in records]


# ---------------------------------------------------------------------------
# sample_paired_sets
# ---------------------------------------------------------------------------


def test_sample_paired_sets_empty_input() -> None:
    """Empty assigned dict and config returns empty list."""
    result = sample_paired_sets({}, {}, seed=42)
    assert result == []


def test_sample_paired_sets_single_valid_bundle() -> None:
    """One bundle with all three tiers produces exactly one triple."""
    cfg = {"experimental_subdomains": {"binder_design": {"paired_sets": 1}}}
    assigned = {
        "benign": _assigned(
            [_rec(source_record_id="b", provenance_bundle_id="bd1")], AssignedTier.BENIGN
        ),
        "borderline": _assigned(
            [_rec(source_record_id="bl", provenance_bundle_id="bd1")], AssignedTier.BORDERLINE
        ),
        "dual_use": _assigned(
            [_rec(source_record_id="du", provenance_bundle_id="bd1")], AssignedTier.DUAL_USE
        ),
    }
    result = sample_paired_sets(assigned, cfg, seed=42)
    assert len(result) == 1
    benign, borderline, dual_use = result[0]
    assert benign.source_record_id == "b"
    assert borderline.source_record_id == "bl"
    assert dual_use.source_record_id == "du"


def test_sample_paired_sets_triple_shares_provenance_bundle_id() -> None:
    """The pairing invariant: every triple must share the same provenance_bundle_id."""
    bundle_ids = ["bd1", "bd2", "bd3"]
    benign_recs = [
        _rec(source_record_id=f"b_{i}", provenance_bundle_id=bid)
        for i, bid in enumerate(bundle_ids)
    ]
    borderline_recs = [
        _rec(source_record_id=f"bl_{i}", provenance_bundle_id=bid)
        for i, bid in enumerate(bundle_ids)
    ]
    dual_use_recs = [
        _rec(source_record_id=f"du_{i}", provenance_bundle_id=bid)
        for i, bid in enumerate(bundle_ids)
    ]

    cfg = {"experimental_subdomains": {"binder_design": {"paired_sets": 3}}}
    assigned = {
        "benign": _assigned(benign_recs, AssignedTier.BENIGN),
        "borderline": _assigned(borderline_recs, AssignedTier.BORDERLINE),
        "dual_use": _assigned(dual_use_recs, AssignedTier.DUAL_USE),
    }
    triples = sample_paired_sets(assigned, cfg, seed=42)
    assert len(triples) == 3
    for benign, borderline, dual_use in triples:
        assert benign.provenance_bundle_id == borderline.provenance_bundle_id, (
            "benign and borderline have different bundle IDs"
        )
        assert benign.provenance_bundle_id == dual_use.provenance_bundle_id, (
            "benign and dual_use have different bundle IDs"
        )


def test_sample_paired_sets_no_cross_bundle_pairing() -> None:
    """Records from different bundles must never be paired together."""
    # Two bundles but only bundle_A has dual_use; bundle_B has no dual_use
    # => only bundle_A should be selected
    assigned = {
        "benign": _assigned(
            [
                _rec(source_record_id="b_A", provenance_bundle_id="bundle_A"),
                _rec(source_record_id="b_B", provenance_bundle_id="bundle_B"),
            ],
            AssignedTier.BENIGN,
        ),
        "borderline": _assigned(
            [
                _rec(source_record_id="bl_A", provenance_bundle_id="bundle_A"),
                _rec(source_record_id="bl_B", provenance_bundle_id="bundle_B"),
            ],
            AssignedTier.BORDERLINE,
        ),
        "dual_use": _assigned(
            [
                _rec(source_record_id="du_A", provenance_bundle_id="bundle_A"),
                # bundle_B intentionally missing from dual_use
            ],
            AssignedTier.DUAL_USE,
        ),
    }
    cfg = {"experimental_subdomains": {"binder_design": {"paired_sets": 10}}}
    triples = sample_paired_sets(assigned, cfg, seed=42)
    assert len(triples) == 1
    benign, _, _ = triples[0]
    assert benign.provenance_bundle_id == "bundle_A"


def test_sample_paired_sets_is_deterministic() -> None:
    """Same seed always produces the same triple order."""
    bundle_ids = [f"b{i}" for i in range(5)]
    benign_recs = [
        _rec(source_record_id=f"ben_{i}", provenance_bundle_id=bid)
        for i, bid in enumerate(bundle_ids)
    ]
    borderline_recs = [
        _rec(source_record_id=f"brl_{i}", provenance_bundle_id=bid)
        for i, bid in enumerate(bundle_ids)
    ]
    dual_recs = [
        _rec(source_record_id=f"du_{i}", provenance_bundle_id=bid)
        for i, bid in enumerate(bundle_ids)
    ]
    cfg = {"experimental_subdomains": {"binder_design": {"paired_sets": 5}}}
    assigned = {
        "benign": _assigned(benign_recs, AssignedTier.BENIGN),
        "borderline": _assigned(borderline_recs, AssignedTier.BORDERLINE),
        "dual_use": _assigned(dual_recs, AssignedTier.DUAL_USE),
    }
    r1 = sample_paired_sets(assigned, cfg, seed=42)
    r2 = sample_paired_sets(assigned, cfg, seed=42)
    assert [b.source_record_id for b, _, _ in r1] == [b.source_record_id for b, _, _ in r2]


def test_sample_paired_sets_respects_target_n() -> None:
    """target_n limits how many triples are returned."""
    bundle_ids = [f"b{i}" for i in range(5)]
    benign_recs = [
        _rec(source_record_id=f"ben_{i}", provenance_bundle_id=bid)
        for i, bid in enumerate(bundle_ids)
    ]
    borderline_recs = [
        _rec(source_record_id=f"brl_{i}", provenance_bundle_id=bid)
        for i, bid in enumerate(bundle_ids)
    ]
    dual_recs = [
        _rec(source_record_id=f"du_{i}", provenance_bundle_id=bid)
        for i, bid in enumerate(bundle_ids)
    ]
    cfg = {"experimental_subdomains": {"binder_design": {"paired_sets": 2}}}
    assigned = {
        "benign": _assigned(benign_recs, AssignedTier.BENIGN),
        "borderline": _assigned(borderline_recs, AssignedTier.BORDERLINE),
        "dual_use": _assigned(dual_recs, AssignedTier.DUAL_USE),
    }
    triples = sample_paired_sets(assigned, cfg, seed=42)
    assert len(triples) == 2


def test_sample_paired_sets_skips_when_no_bundles_span_all_tiers() -> None:
    """If no bundle spans all three tiers, subdomain is skipped and result is empty."""
    cfg = {"experimental_subdomains": {"binder_design": {"paired_sets": 1}}}
    # Only benign + borderline, no dual_use
    assigned = {
        "benign": _assigned(
            [_rec(source_record_id="b", provenance_bundle_id="bd1")], AssignedTier.BENIGN
        ),
        "borderline": _assigned(
            [_rec(source_record_id="bl", provenance_bundle_id="bd1")], AssignedTier.BORDERLINE
        ),
        "dual_use": [],
    }
    result = sample_paired_sets(assigned, cfg, seed=42)
    assert result == []


def test_ot_style_per_target_bundle_ids_produce_no_triples() -> None:
    """Regression: OT catalogue assigns bundle_id = target_id (one record per bundle).

    With per-target bundle IDs, no bundle spans all three tiers, so sampling
    correctly returns [] rather than silently forming biologically unrelated
    triples.  This is the honest failure mode we want while bundle_definitions.csv
    is being designed.
    """
    cfg = {"experimental_subdomains": {"binder_design": {"paired_sets": 5}}}
    # Simulate _build_ot_catalogue output: each record gets its own target_id as bundle
    benign_recs = [
        _rec(source_record_id=f"ENSG{i:011d}", provenance_bundle_id=f"ENSG{i:011d}")
        for i in range(5)
    ]
    borderline_recs = [
        _rec(source_record_id=f"ENSG{i + 10:011d}", provenance_bundle_id=f"ENSG{i + 10:011d}")
        for i in range(5)
    ]
    dual_use_recs = [
        _rec(source_record_id=f"ENSG{i + 20:011d}", provenance_bundle_id=f"ENSG{i + 20:011d}")
        for i in range(5)
    ]
    assigned = {
        "benign": _assigned(benign_recs, AssignedTier.BENIGN),
        "borderline": _assigned(borderline_recs, AssignedTier.BORDERLINE),
        "dual_use": _assigned(dual_use_recs, AssignedTier.DUAL_USE),
    }
    result = sample_paired_sets(assigned, cfg, seed=42)
    assert result == [], (
        "Per-target bundle IDs must produce no triples — "
        "valid triples require explicit bundle_definitions.csv"
    )


def test_sample_paired_sets_min_wins_when_fewer_bundles_than_target() -> None:
    """If only 1 valid bundle exists but target_n=5, return 1 (not crash)."""
    cfg = {"experimental_subdomains": {"binder_design": {"paired_sets": 5}}}
    assigned = {
        "benign": _assigned(
            [_rec(source_record_id="b", provenance_bundle_id="bd1")], AssignedTier.BENIGN
        ),
        "borderline": _assigned(
            [_rec(source_record_id="bl", provenance_bundle_id="bd1")], AssignedTier.BORDERLINE
        ),
        "dual_use": _assigned(
            [_rec(source_record_id="du", provenance_bundle_id="bd1")], AssignedTier.DUAL_USE
        ),
    }
    triples = sample_paired_sets(assigned, cfg, seed=42)
    assert len(triples) == 1


# ---------------------------------------------------------------------------
# sample_controls
# ---------------------------------------------------------------------------


def test_sample_controls_empty_input() -> None:
    result = sample_controls({}, {}, seed=42)
    assert result == []


def test_sample_controls_returns_benign_only() -> None:
    cfg = {"control_subdomains": {"bioinformatics_scripting": {"benign_only": 2}}}
    recs = [
        _rec(subdomain="bioinformatics_scripting", source_record_id=f"ctrl_{i}") for i in range(5)
    ]
    assigned = {"benign": _assigned(recs, AssignedTier.BENIGN)}
    controls = sample_controls(assigned, cfg, seed=42)
    assert len(controls) == 2
    assert all(r.subdomain == "bioinformatics_scripting" for r in controls)


def test_sample_controls_is_deterministic() -> None:
    cfg = {"control_subdomains": {"bioinformatics_scripting": {"benign_only": 3}}}
    recs = [
        _rec(subdomain="bioinformatics_scripting", source_record_id=f"ctrl_{i}") for i in range(10)
    ]
    assigned = {"benign": _assigned(recs, AssignedTier.BENIGN)}
    r1 = sample_controls(assigned, cfg, seed=42)
    r2 = sample_controls(assigned, cfg, seed=42)
    assert [r.source_record_id for r in r1] == [r.source_record_id for r in r2]
