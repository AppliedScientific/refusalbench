"""Tests for analysis/longitudinal.py — cross-snapshot comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from refusalbench.analysis.longitudinal import cochran_q_across_snapshots, compare_snapshots

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_snapshot(
    tmp_path: Path,
    label: str,
    rows: list[dict],
    lineage_map: dict[str, str] | None = None,
) -> Path:
    """Write a minimal snapshot directory with adjudicated.csv and manifest.json."""
    snap = tmp_path / label
    (snap / "council").mkdir(parents=True)

    df = pd.DataFrame(rows)
    df.to_csv(snap / "council" / "adjudicated.csv", index=False)

    manifest = {
        "snapshot_label": label,
        "started_at": "2026-05-01T00:00:00Z",
        "completed_at": "2026-05-01T01:00:00Z",
        "prompt_version": "v1.0",
        "council_version": "v1.0",
        "git_sha": "abc123",
        "seed": 42,
        "n_prompts": len(df["prompt_id"].unique()) if not df.empty else 0,
        "n_trials": 1,
    }
    (snap / "manifest.json").write_text(json.dumps(manifest))
    return snap


def _write_lineage_config(tmp_path: Path, lineage_map: dict[str, str]) -> Path:
    """Write a minimal model_lineage.json mapping model_id -> lineage name."""
    lineages = {}
    for model_id, lineage_name in lineage_map.items():
        if lineage_name not in lineages:
            lineages[lineage_name] = {
                "display": lineage_name,
                "organization": "test",
                "jurisdiction": "test",
                "members": [],
            }
        lineages[lineage_name]["members"].append(
            {"model_id": model_id, "display_name": model_id, "release_date": "2026-01-01"}
        )
    cfg = {"schema_doc": "test", "lineages": lineages}
    p = tmp_path / "model_lineage.json"
    p.write_text(json.dumps(cfg))
    return p


# ---------------------------------------------------------------------------
# compare_snapshots — lineage grouping
# ---------------------------------------------------------------------------


def _make_rows(
    model_id: str, subdomain: str, tier: str, n_refused: int, n_compliant: int
) -> list[dict]:
    rows = []
    for i in range(n_refused):
        rows.append(
            {
                "prompt_id": f"p{i}",
                "model": model_id,
                "trial_idx": 0,
                "subdomain": subdomain,
                "tier": tier,
                "modal_compliance": "direct_refusal",
            }
        )
    for i in range(n_compliant):
        rows.append(
            {
                "prompt_id": f"q{i}",
                "model": model_id,
                "trial_idx": 0,
                "subdomain": subdomain,
                "tier": tier,
                "modal_compliance": "compliance",
            }
        )
    return rows


def test_compare_snapshots_same_panel_rates(tmp_path: Path) -> None:
    """Refusal rates are computed correctly for matching model panels."""
    rows_a = _make_rows("model-x", "binder_design", "benign", n_refused=3, n_compliant=7)
    rows_b = _make_rows("model-x", "binder_design", "benign", n_refused=8, n_compliant=2)
    snap_a = _write_snapshot(tmp_path, "2026-05", rows_a)
    snap_b = _write_snapshot(tmp_path, "2026-08", rows_b)
    lineage_cfg = _write_lineage_config(tmp_path, {"model-x": "lineage-x"})

    result = compare_snapshots(snap_a, snap_b, lineage_config=lineage_cfg)

    assert len(result) == 1
    row = result.iloc[0]
    assert row["lineage"] == "lineage-x"
    assert abs(row["rate_a"] - 0.3) < 1e-9
    assert abs(row["rate_b"] - 0.8) < 1e-9
    assert abs(row["delta"] - 0.5) < 1e-9


def test_compare_snapshots_different_model_ids_same_lineage(tmp_path: Path) -> None:
    """
    When snapshot A has model-v1 and snapshot B has model-v2, but both belong to
    the same lineage, compare_snapshots must return ONE row for that lineage —
    not two rows split by model_id.

    This is the critical property for living-benchmark longitudinal comparison:
    Opus 4.7 and Opus 4.8 should appear in the same anthropic-opus row.
    """
    rows_a = _make_rows("model-v1", "binder_design", "benign", n_refused=4, n_compliant=6)
    rows_b = _make_rows("model-v2", "binder_design", "benign", n_refused=6, n_compliant=4)
    snap_a = _write_snapshot(tmp_path, "2026-05", rows_a)
    snap_b = _write_snapshot(tmp_path, "2026-08", rows_b)

    # Both model-v1 and model-v2 map to the same lineage
    lineage_cfg = _write_lineage_config(
        tmp_path,
        {
            "model-v1": "provider-flagship",
            "model-v2": "provider-flagship",
        },
    )

    result = compare_snapshots(snap_a, snap_b, lineage_config=lineage_cfg)

    # Must be exactly one row — NOT two rows (one per model_id)
    assert len(result) == 1, (
        f"Expected 1 row (same lineage), got {len(result)}. "
        f"Lineages found: {result['lineage'].tolist()}"
    )
    assert result.iloc[0]["lineage"] == "provider-flagship"
    assert abs(result.iloc[0]["rate_a"] - 0.4) < 1e-9
    assert abs(result.iloc[0]["rate_b"] - 0.6) < 1e-9


def test_compare_snapshots_different_lineages_produce_separate_rows(tmp_path: Path) -> None:
    """Different lineages in the same snapshot each get their own row."""
    rows_a = _make_rows(
        "model-a", "binder_design", "benign", n_refused=2, n_compliant=8
    ) + _make_rows("model-b", "binder_design", "benign", n_refused=9, n_compliant=1)
    rows_b = _make_rows(
        "model-a", "binder_design", "benign", n_refused=1, n_compliant=9
    ) + _make_rows("model-b", "binder_design", "benign", n_refused=7, n_compliant=3)
    snap_a = _write_snapshot(tmp_path, "2026-05", rows_a)
    snap_b = _write_snapshot(tmp_path, "2026-08", rows_b)
    lineage_cfg = _write_lineage_config(
        tmp_path,
        {
            "model-a": "lineage-a",
            "model-b": "lineage-b",
        },
    )

    result = compare_snapshots(snap_a, snap_b, lineage_config=lineage_cfg)

    assert len(result) == 2
    assert set(result["lineage"]) == {"lineage-a", "lineage-b"}


def test_compare_snapshots_model_absent_from_one_snapshot(tmp_path: Path) -> None:
    """A lineage present in only one snapshot still gets a row (with NaN for the missing side)."""
    rows_a = _make_rows("model-x", "binder_design", "benign", n_refused=5, n_compliant=5)
    rows_b = _make_rows("model-y", "binder_design", "benign", n_refused=3, n_compliant=7)
    snap_a = _write_snapshot(tmp_path, "2026-05", rows_a)
    snap_b = _write_snapshot(tmp_path, "2026-08", rows_b)
    lineage_cfg = _write_lineage_config(
        tmp_path,
        {
            "model-x": "lineage-x",
            "model-y": "lineage-y",
        },
    )

    result = compare_snapshots(snap_a, snap_b, lineage_config=lineage_cfg)

    assert len(result) == 2
    row_x = result[result["lineage"] == "lineage-x"].iloc[0]
    row_y = result[result["lineage"] == "lineage-y"].iloc[0]
    assert abs(row_x["rate_a"] - 0.5) < 1e-9
    assert pd.isna(row_x["rate_b"])
    assert pd.isna(row_y["rate_a"])
    assert abs(row_y["rate_b"] - 0.3) < 1e-9


# ---------------------------------------------------------------------------
# cochran_q_across_snapshots
# ---------------------------------------------------------------------------


def test_cochran_q_requires_three_snapshots(tmp_path: Path) -> None:
    snap = _write_snapshot(tmp_path, "2026-05", [])
    with pytest.raises(ValueError, match="at least 3"):
        cochran_q_across_snapshots([snap, snap])


def test_cochran_q_returns_expected_keys(tmp_path: Path) -> None:
    def make_snap(label: str, n_refused: int, n_compliant: int) -> Path:
        rows = _make_rows("model-x", "binder_design", "benign", n_refused, n_compliant)
        return _write_snapshot(tmp_path, label, rows)

    snaps = [make_snap("2026-02", 8, 2), make_snap("2026-05", 5, 5), make_snap("2026-08", 2, 8)]
    lineage_cfg = _write_lineage_config(tmp_path, {"model-x": "lineage-x"})

    result = cochran_q_across_snapshots(
        snaps,
        model_filter="lineage-x",
        subdomain_filter="binder_design",
        lineage_config=lineage_cfg,
    )

    for key in (
        "q_statistic",
        "p_value",
        "df",
        "snapshots",
        "per_snapshot_rates",
        "mcnemar_pairwise",
    ):
        assert key in result, f"Missing key: {key}"
    assert result["df"] == 2  # k-1 = 3-1
    assert len(result["snapshots"]) == 3
    assert len(result["per_snapshot_rates"]) == 3
    assert len(result["mcnemar_pairwise"]) == 3  # C(3,2)
