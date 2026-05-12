"""Cross-snapshot longitudinal analysis for the living benchmark.

Two entry points:

    compare_snapshots(a, b)          — per-(lineage, subdomain, tier) rate delta
    cochran_q_across_snapshots(...)  — Cochran's Q for trajectory across ≥3 snapshots

Both functions are pure: they read CSVs and return DataFrames / dicts. No side effects.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_REFUSAL_LABELS = {"direct_refusal", "non_responsive"}


def _load_snapshot(snap_dir: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    """Return (manifest, adjudicated_results_df) for one snapshot.

    The adjudicated CSV is expected at snap_dir/council/adjudicated.csv with
    columns: prompt_id, model, trial_idx, modal_compliance, subdomain, tier.
    Falls back to snap_dir/eval/ raw CSVs with no council label (compliance=None).
    """
    manifest_path = snap_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.json in {snap_dir}")
    manifest = json.loads(manifest_path.read_text())

    adjudicated = snap_dir / "council" / "adjudicated.csv"
    if adjudicated.exists():
        df = pd.read_csv(adjudicated)
    else:
        # Fallback: concatenate raw eval CSVs, mark compliance as unknown
        frames = []
        for csv_path in sorted((snap_dir / "eval").glob("*.csv")):
            frame = pd.read_csv(csv_path)
            frames.append(frame)
        if not frames:
            raise FileNotFoundError(f"No eval CSVs found in {snap_dir}/eval/")
        df = pd.concat(frames, ignore_index=True)
        df["modal_compliance"] = None

    df["snapshot"] = manifest["snapshot_label"]
    return manifest, df


def _attach_lineage(df: pd.DataFrame, lineage_path: Path) -> pd.DataFrame:
    """Add a 'lineage' column by joining on model_id."""
    lineage_cfg = json.loads(lineage_path.read_text())
    id_to_lineage: dict[str, str] = {}
    for lineage_name, entry in lineage_cfg["lineages"].items():
        for member in entry["members"]:
            id_to_lineage[member["model_id"]] = lineage_name
    df = df.copy()
    df["lineage"] = df["model"].map(id_to_lineage).fillna(df["model"])
    return df


def _refusal_rate(df: pd.DataFrame, compliance_col: str = "modal_compliance") -> float:
    if df.empty:
        return float("nan")
    refused = df[compliance_col].isin(_REFUSAL_LABELS).sum()
    return float(refused) / len(df)


def _bootstrap_ci(
    values: np.ndarray,
    n_boot: int = 2000,
    ci: float = 0.95,
    rng: np.random.Generator | None = None,
) -> tuple[float, float]:
    if rng is None:
        rng = np.random.default_rng(42)
    boots = np.array(
        [values[rng.integers(0, len(values), len(values))].mean() for _ in range(n_boot)]
    )
    lo = float(np.percentile(boots, (1 - ci) / 2 * 100))
    hi = float(np.percentile(boots, (1 + ci) / 2 * 100))
    return lo, hi


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compare_snapshots(
    snapshot_a: Path,
    snapshot_b: Path,
    *,
    lineage_config: Path | None = None,
    group_by: list[str] | None = None,
    compliance_col: str = "modal_compliance",
) -> pd.DataFrame:
    """Compare refusal rates between two snapshots.

    Returns one row per (lineage, subdomain, tier) combination with columns:
        lineage, subdomain, tier,
        rate_a, rate_b, delta,
        ci_lo_a, ci_hi_a, ci_lo_b, ci_hi_b,
        n_a, n_b

    Parameters
    ----------
    snapshot_a, snapshot_b:
        Paths to snapshot directories (e.g. snapshots/2026-05/).
    lineage_config:
        Path to config/model_lineage.json. Defaults to <project_root>/config/model_lineage.json.
    group_by:
        Columns to group on (default: ["lineage", "subdomain", "tier"]).
    compliance_col:
        Column containing MUSE compliance label.

    Example
    -------
    >>> from pathlib import Path
    >>> # compare_snapshots(Path("snapshots/2026-05"), Path("snapshots/2026-08"))
    """
    if lineage_config is None:
        lineage_config = (
            Path(__file__).resolve().parents[3] / "benchmark" / "config" / "model_lineage.json"
        )
    if group_by is None:
        group_by = ["lineage", "subdomain", "tier"]

    _, df_a = _load_snapshot(snapshot_a)
    _, df_b = _load_snapshot(snapshot_b)

    if lineage_config.exists():
        df_a = _attach_lineage(df_a, lineage_config)
        df_b = _attach_lineage(df_b, lineage_config)

    rows = []
    groups_a = df_a.groupby(group_by)
    groups_b = df_b.groupby(group_by)
    all_keys = sorted(set(groups_a.groups) | set(groups_b.groups), key=str)

    for key in all_keys:
        g_a = groups_a.get_group(key) if key in groups_a.groups else pd.DataFrame()
        g_b = groups_b.get_group(key) if key in groups_b.groups else pd.DataFrame()

        refused_a: np.ndarray[tuple[Any, ...], np.dtype[np.float64]] = (
            np.asarray(g_a[compliance_col].isin(_REFUSAL_LABELS).astype(float).values, dtype=float)
            if not g_a.empty
            else np.array([], dtype=float)
        )
        refused_b: np.ndarray[tuple[Any, ...], np.dtype[np.float64]] = (
            np.asarray(g_b[compliance_col].isin(_REFUSAL_LABELS).astype(float).values, dtype=float)
            if not g_b.empty
            else np.array([], dtype=float)
        )

        rate_a = float(refused_a.mean()) if len(refused_a) else float("nan")
        rate_b = float(refused_b.mean()) if len(refused_b) else float("nan")
        ci_a = _bootstrap_ci(refused_a) if len(refused_a) >= 2 else (float("nan"), float("nan"))
        ci_b = _bootstrap_ci(refused_b) if len(refused_b) >= 2 else (float("nan"), float("nan"))

        row: dict[str, Any] = {}
        for i, col in enumerate(group_by):
            row[col] = key[i] if len(group_by) > 1 else key  # type: ignore[index]
        row.update(
            rate_a=rate_a,
            rate_b=rate_b,
            delta=rate_b - rate_a if not (np.isnan(rate_a) or np.isnan(rate_b)) else float("nan"),
            ci_lo_a=ci_a[0],
            ci_hi_a=ci_a[1],
            ci_lo_b=ci_b[0],
            ci_hi_b=ci_b[1],
            n_a=len(g_a),
            n_b=len(g_b),
        )
        rows.append(row)

    return pd.DataFrame(rows)


def cochran_q_across_snapshots(
    snapshot_dirs: list[Path],
    *,
    model_filter: str | None = None,
    subdomain_filter: str | None = None,
    tier_filter: str = "benign",
    compliance_col: str = "modal_compliance",
    lineage_config: Path | None = None,
) -> dict[str, Any]:
    """Cochran's Q test across ≥3 snapshots for a given model/subdomain slice.

    Returns a dict with keys:
        q_statistic, p_value, df, snapshots (list of labels),
        per_snapshot_rates (list of floats), mcnemar_pairwise (list of dicts)

    Parameters
    ----------
    snapshot_dirs:
        Ordered list of snapshot directories, oldest first.
    model_filter:
        model_id or lineage name to restrict to (all models if None).
    subdomain_filter:
        Subdomain to restrict to (all subdomains if None).
    tier_filter:
        Tier to restrict to (default: "benign").
    compliance_col:
        Column containing MUSE compliance label.
    lineage_config:
        Path to config/model_lineage.json.

    Example
    -------
    >>> # cochran_q_across_snapshots(
    >>> #     [Path("snapshots/2026-05"), Path("snapshots/2026-08"), Path("snapshots/2026-11")],
    >>> #     model_filter="anthropic-opus", subdomain_filter="binder_design",
    >>> # )
    """
    if len(snapshot_dirs) < 3:
        raise ValueError("Cochran's Q requires at least 3 snapshots.")
    if lineage_config is None:
        lineage_config = (
            Path(__file__).resolve().parents[3]
            / "benchmark"
            / "config"
            / "model_lineage.json"
        )

    frames = []
    labels = []
    for sd in snapshot_dirs:
        manifest, df = _load_snapshot(sd)
        if lineage_config.exists():
            df = _attach_lineage(df, lineage_config)
        if subdomain_filter:
            df = df[df.get("subdomain", pd.Series(dtype=str)) == subdomain_filter]
        if tier_filter:
            df = df[df.get("tier", pd.Series(dtype=str)) == tier_filter]
        if model_filter:
            mask = (df.get("model", pd.Series(dtype=str)) == model_filter) | (
                df.get("lineage", pd.Series(dtype=str)) == model_filter
            )
            df = df[mask]
        df["refused"] = df[compliance_col].isin(_REFUSAL_LABELS).astype(int)
        frames.append(df)
        labels.append(manifest["snapshot_label"])

    # Align on prompt_id — only prompts present in all snapshots
    common_prompts = set(frames[0]["prompt_id"])
    for df in frames[1:]:
        common_prompts &= set(df["prompt_id"])
    aligned = [
        df[df["prompt_id"].isin(common_prompts)].groupby("prompt_id")["refused"].mean()
        for df in frames
    ]

    # Build k x n matrix (k snapshots, n prompts)
    prompt_ids = sorted(common_prompts)
    matrix = np.array([[s.get(p, float("nan")) for p in prompt_ids] for s in aligned])
    valid = ~np.isnan(matrix).any(axis=0)
    matrix = (matrix[:, valid] >= 0.5).astype(int)

    k, n = matrix.shape
    row_sums = matrix.sum(axis=1)  # per-snapshot totals
    col_sums = matrix.sum(axis=0)  # per-prompt totals
    grand = matrix.sum()

    # Cochran's Q
    q = (k - 1) * (k * (row_sums**2).sum() - grand**2) / (k * grand - (col_sums**2).sum())
    df_q = k - 1
    p_value = float(1 - stats.chi2.cdf(q, df_q))

    per_snapshot_rates = [float(row_sums[i]) / n for i in range(k)]

    # Pairwise McNemar's tests
    pairwise = []
    for i in range(k):
        for j in range(i + 1, k):
            b = int(((matrix[i] == 1) & (matrix[j] == 0)).sum())
            c = int(((matrix[i] == 0) & (matrix[j] == 1)).sum())
            if b + c == 0:
                mn_p = 1.0
            else:
                mn_result = stats.binomtest(b, b + c, 0.5, alternative="two-sided")
                mn_p = float(mn_result.pvalue)
            pairwise.append(
                {
                    "snapshot_a": labels[i],
                    "snapshot_b": labels[j],
                    "rate_a": per_snapshot_rates[i],
                    "rate_b": per_snapshot_rates[j],
                    "delta": per_snapshot_rates[j] - per_snapshot_rates[i],
                    "p_value": mn_p,
                }
            )

    return {
        "q_statistic": float(q),
        "p_value": p_value,
        "df": df_q,
        "n_prompts": n,
        "snapshots": labels,
        "per_snapshot_rates": per_snapshot_rates,
        "mcnemar_pairwise": pairwise,
    }
