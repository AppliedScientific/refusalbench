"""Tests for the render-all pipeline: round-trip, ID stability, pairing invariants."""

from __future__ import annotations

import json
from pathlib import Path

from refusalbench.prompt_build.catalogue import CandidateRecord, RiskAnnotation
from refusalbench.prompt_build.pipeline import _make_prompt_id, render_all
from refusalbench.prompt_build.rendering import _DEFAULT_TEMPLATE_CONFIG
from refusalbench.prompts import Tier, load_prompts

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rec(
    *,
    subdomain: str = "binder_design",
    source_record_id: str = "rec001",
    provenance_bundle_id: str = "bundle001",
    target_name: str = "HER2",
    target_class: str = "receptor_tyrosine_kinase",
    bsl: int = 1,
    **kwargs: object,
) -> CandidateRecord:
    return CandidateRecord(
        source_record_id=source_record_id,
        provenance_bundle_id=provenance_bundle_id,
        subdomain=subdomain,
        target_name=target_name,
        target_class=target_class,
        organism_name="Homo sapiens",
        source_database="open_targets",
        source_version="24.06",
        natural_language_summary="test record",
        risk=RiskAnnotation(organism_bsl=bsl),
        **kwargs,  # type: ignore[arg-type]
    )


def _triple(
    *, subdomain: str = "binder_design", bundle: str = "bundle001"
) -> tuple[CandidateRecord, CandidateRecord, CandidateRecord]:
    """Return a (benign, borderline, dual_use) triple sharing the same bundle."""
    return (
        _rec(subdomain=subdomain, source_record_id="rec_b", provenance_bundle_id=bundle, bsl=1),
        _rec(subdomain=subdomain, source_record_id="rec_bl", provenance_bundle_id=bundle, bsl=3),
        _rec(subdomain=subdomain, source_record_id="rec_du", provenance_bundle_id=bundle, bsl=4),
    )


# ---------------------------------------------------------------------------
# Round-trip: render → write JSON → load via prompts.py → check equality
# ---------------------------------------------------------------------------


def test_round_trip_renders_and_loads(tmp_path: Path) -> None:
    """Prompt dict written by render_all must survive load_prompts validation."""
    triple = _triple()
    prompt_dicts = render_all(
        [triple],
        [],
        template_cfg_path=_DEFAULT_TEMPLATE_CONFIG,
        seed=42,
    )
    assert len(prompt_dicts) == 3

    root = tmp_path / "prompts"
    for d in prompt_dicts:
        tier_dir = root / "v1.0" / str(d["tier"])
        tier_dir.mkdir(parents=True, exist_ok=True)
        pid = str(d["prompt_id"])
        (tier_dir / f"{pid}.json").write_text(json.dumps(d))

    loaded = load_prompts("1.0", root)
    assert len(loaded) == 3


def test_round_trip_preserves_prompt_id(tmp_path: Path) -> None:
    """prompt_id survives the JSON round-trip without mutation."""
    triple = _triple()
    prompt_dicts = render_all(
        [triple],
        [],
        template_cfg_path=_DEFAULT_TEMPLATE_CONFIG,
        seed=42,
    )
    root = tmp_path / "prompts"
    for d in prompt_dicts:
        tier_dir = root / "v1.0" / str(d["tier"])
        tier_dir.mkdir(parents=True, exist_ok=True)
        pid = str(d["prompt_id"])
        (tier_dir / f"{pid}.json").write_text(json.dumps(d))

    loaded = load_prompts("1.0", root)
    rendered_ids = {str(d["prompt_id"]) for d in prompt_dicts}
    loaded_ids = {p.prompt_id for p in loaded}
    assert rendered_ids == loaded_ids


def test_round_trip_preserves_paired_with(tmp_path: Path) -> None:
    """paired_with cross-references survive the JSON round-trip."""
    triple = _triple()
    prompt_dicts = render_all(
        [triple],
        [],
        template_cfg_path=_DEFAULT_TEMPLATE_CONFIG,
        seed=42,
    )
    root = tmp_path / "prompts"
    for d in prompt_dicts:
        tier_dir = root / "v1.0" / str(d["tier"])
        tier_dir.mkdir(parents=True, exist_ok=True)
        pid = str(d["prompt_id"])
        (tier_dir / f"{pid}.json").write_text(json.dumps(d))

    # load_prompts validates paired_with reciprocity — if it passes, round-trip is valid
    loaded = load_prompts("1.0", root)
    assert all(len(p.paired_with) == 2 for p in loaded)


def test_round_trip_provenance_preserved(tmp_path: Path) -> None:
    """_provenance block survives the round-trip and surfaces as Prompt.provenance."""
    triple = _triple()
    prompt_dicts = render_all(
        [triple],
        [],
        template_cfg_path=_DEFAULT_TEMPLATE_CONFIG,
        seed=42,
    )
    root = tmp_path / "prompts"
    for d in prompt_dicts:
        tier_dir = root / "v1.0" / str(d["tier"])
        tier_dir.mkdir(parents=True, exist_ok=True)
        pid = str(d["prompt_id"])
        (tier_dir / f"{pid}.json").write_text(json.dumps(d))

    loaded = load_prompts("1.0", root)
    for p in loaded:
        assert p.provenance is not None, f"{p.prompt_id} has no provenance"
        assert "source_record_id" in p.provenance


def test_round_trip_tiers_span_all_three(tmp_path: Path) -> None:
    """After loading, the three tiers are exactly benign, borderline, dual_use."""
    triple = _triple()
    prompt_dicts = render_all(
        [triple],
        [],
        template_cfg_path=_DEFAULT_TEMPLATE_CONFIG,
        seed=42,
    )
    root = tmp_path / "prompts"
    for d in prompt_dicts:
        tier_dir = root / "v1.0" / str(d["tier"])
        tier_dir.mkdir(parents=True, exist_ok=True)
        pid = str(d["prompt_id"])
        (tier_dir / f"{pid}.json").write_text(json.dumps(d))

    loaded = load_prompts("1.0", root)
    tiers = {p.tier for p in loaded}
    assert tiers == {Tier.BENIGN, Tier.BORDERLINE, Tier.DUAL_USE}


# ---------------------------------------------------------------------------
# Content-derived prompt ID stability
# ---------------------------------------------------------------------------


def test_make_prompt_id_is_stable() -> None:
    """Same inputs always produce the same ID."""
    rec = _rec(source_record_id="rec001", subdomain="binder_design")
    id1 = _make_prompt_id(rec, "benign", 42)
    id2 = _make_prompt_id(rec, "benign", 42)
    assert id1 == id2


def test_make_prompt_id_differs_by_tier() -> None:
    """benign and dual_use IDs must be different for the same record."""
    rec = _rec(source_record_id="rec001", subdomain="binder_design")
    assert _make_prompt_id(rec, "benign", 42) != _make_prompt_id(rec, "dual_use", 42)


def test_make_prompt_id_differs_by_record() -> None:
    """Different source_record_ids produce different IDs."""
    rec_a = _rec(source_record_id="recA")
    rec_b = _rec(source_record_id="recB")
    assert _make_prompt_id(rec_a, "benign", 42) != _make_prompt_id(rec_b, "benign", 42)


def test_make_prompt_id_is_independent_of_insertion_order() -> None:
    """Adding another record to the catalogue must not change existing IDs."""
    rec = _rec(source_record_id="rec001", subdomain="binder_design")
    id_before = _make_prompt_id(rec, "benign", 42)
    # "Insert" another record (simulated by computing another ID)
    _make_prompt_id(_rec(source_record_id="rec999"), "benign", 42)
    id_after = _make_prompt_id(rec, "benign", 42)
    assert id_before == id_after


def test_make_prompt_id_no_separator_collision() -> None:
    """The \x1f separator prevents hash collisions across field boundaries."""
    # ("a1", "benign", "23") vs ("a", "1benign", "23")
    rec_a = _rec(source_record_id="a1", subdomain="a")
    rec_b = _rec(source_record_id="a", subdomain="a")
    id_a = _make_prompt_id(rec_a, "benign23", 0)
    id_b = _make_prompt_id(rec_b, "1benign23", 0)
    assert id_a != id_b


# ---------------------------------------------------------------------------
# Cross-tier target consistency (pairing invariant)
# ---------------------------------------------------------------------------


def test_render_all_triple_shares_subdomain(tmp_path: Path) -> None:
    """All three prompts in a triple have the same subdomain."""
    triple = _triple(subdomain="binder_design")
    prompt_dicts = render_all(
        [triple],
        [],
        template_cfg_path=_DEFAULT_TEMPLATE_CONFIG,
        seed=42,
    )
    subdomains = {str(d["subdomain"]) for d in prompt_dicts}
    assert subdomains == {"binder_design"}


def test_render_all_multi_triple_produces_independent_ids(tmp_path: Path) -> None:
    """Two triples with different bundles produce six unique prompt IDs."""
    t1 = _triple(bundle="bundle001")
    t2 = _triple(
        bundle="bundle002",
        subdomain="binder_design",
    )
    # Use distinct source_record_ids to avoid ID collision
    t2 = (
        _rec(source_record_id="rec2_b", provenance_bundle_id="bundle002"),
        _rec(source_record_id="rec2_bl", provenance_bundle_id="bundle002", bsl=3),
        _rec(source_record_id="rec2_du", provenance_bundle_id="bundle002", bsl=4),
    )
    prompt_dicts = render_all(
        [t1, t2],
        [],
        template_cfg_path=_DEFAULT_TEMPLATE_CONFIG,
        seed=42,
    )
    assert len(prompt_dicts) == 6
    ids = [str(d["prompt_id"]) for d in prompt_dicts]
    assert len(ids) == len(set(ids)), "Duplicate prompt IDs across triples"


def test_render_all_control_has_empty_paired_with(tmp_path: Path) -> None:
    """Controls rendered from sample_controls have an empty paired_with list."""
    control = _rec(
        source_record_id="ctrl001",
        subdomain="bioinformatics_scripting",
        additional_fields={
            "task_description": "parse multi-FASTA files and compute per-sequence GC content",
            "tool_ecosystem": "BioPython and pandas",
            "input_description": "multi-FASTA nucleotide sequences",
            "output_description": "TSV table with sequence ID and GC percentage",
        },
    )
    prompt_dicts = render_all(
        [],
        [control],
        template_cfg_path=_DEFAULT_TEMPLATE_CONFIG,
        seed=42,
    )
    assert len(prompt_dicts) == 1
    assert prompt_dicts[0]["paired_with"] == []


def test_render_all_returns_empty_for_empty_input() -> None:
    """render_all with no triples and no controls returns []."""
    result = render_all([], [], template_cfg_path=_DEFAULT_TEMPLATE_CONFIG)
    assert result == []
