"""Six publication-quality figures for the RefusalBench paper.

All functions read from DataFrames (no direct file I/O) and return a
matplotlib Figure. The CLI entry point saves PDF + PNG.

Run all: ``python -m refusalbench.analysis.figures --all --results-dir results/snapshots/2026-05``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import matplotlib as mpl
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Global typography — Times New Roman (falls back to Times → DejaVu Serif)
# ---------------------------------------------------------------------------
mpl.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "axes.titlesize": 12,
        "axes.labelsize": 11,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "legend.title_fontsize": 9,
    }
)

# ---------------------------------------------------------------------------
# Provider colour palette — full 19-model panel
# ---------------------------------------------------------------------------
_PROVIDER_COLORS: dict[str, str] = {
    "anthropic": "#E53E3E",  # red
    "openai": "#38A169",  # green
    "google": "#3182CE",  # blue
    "amazon": "#DD6B20",  # orange
    "meta": "#805AD5",  # purple
    "mistral": "#2B6CB0",  # darker blue
    "deepseek": "#2C7A7B",  # teal
    "qwen": "#D69E2E",  # gold
    "zai": "#319795",  # teal-green
    "xai": "#4A5568",  # dark slate
    "moonshot": "#D53F8C",  # pink
    "minimax": "#6B46C1",  # deep purple
    "nvidia": "#76B900",  # NVIDIA green
    # legacy aliases
    "zhipu": "#319795",
    "other": "#718096",  # gray
}

# ---------------------------------------------------------------------------
# Model-ID → (short display name, provider) — keyed on adjudicated.csv values
# ---------------------------------------------------------------------------
_MODEL_META: dict[str, tuple[str, str]] = {
    "anthropic/claude-opus-4.7": ("Opus 4.7", "anthropic"),
    "anthropic/claude-opus-4.6": ("Opus 4.6", "anthropic"),
    "anthropic/claude-opus-4.5": ("Opus 4.5", "anthropic"),
    "anthropic/claude-sonnet-4.6": ("Sonnet 4.6", "anthropic"),
    "openai/gpt-5.5-20260423": ("GPT-5.5", "openai"),
    "openai/gpt-5.4-mini-20260317": ("GPT-5.4 Mini", "openai"),
    "google/gemini-3.1-pro-preview-20260219": ("Gemini 3.1 Pro", "google"),
    "google/gemini-3.1-flash-lite-20260507": ("Gemini Flash Lite", "google"),
    "x-ai/grok-4.20-20260309": ("Grok 4.20", "xai"),
    "moonshotai/kimi-k2.6-20260420": ("Kimi K2.6", "moonshot"),
    "minimax/minimax-m2.7-20260318": ("MiniMax M2.7", "minimax"),
    "us.amazon.nova-pro-v1:0": ("Nova Pro", "amazon"),
    "us.meta.llama3-3-70b-instruct-v1:0": ("Llama 3.3 70B", "meta"),
    "mistral.mistral-large-3-675b-instruct": ("Mistral Large 3", "mistral"),
    "deepseek.v3.2": ("DeepSeek V3.2", "deepseek"),
    "us.deepseek.r1-v1:0": ("DeepSeek R1", "deepseek"),
    "qwen.qwen3-next-80b-a3b": ("Qwen3 80B", "qwen"),
    "zai.glm-5": ("GLM-5", "zai"),
    "nvidia.nemotron-super-3-120b": ("Nemotron 120B", "nvidia"),
}

_FIGURE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "results" / "figures"

# Tier display ordering
_TIERS = ["benign", "borderline", "dual_use"]
_TIER_COLORS = {
    "benign": "#68D391",  # green
    "borderline": "#F6AD55",  # amber
    "dual_use": "#FC8181",  # red
}
_TIER_LABELS = {
    "benign": "Benign",
    "borderline": "Borderline",
    "dual_use": "Dual-use",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _provider_color(provider: str) -> str:
    return _PROVIDER_COLORS.get(provider.lower(), _PROVIDER_COLORS["other"])


def _wilson_ci(
    n_refused: int | float, n_total: int | float, z: float = 1.96
) -> tuple[float, float, float]:
    """Return (rate, ci_lo, ci_hi) using Wilson score interval."""
    if n_total == 0:
        return 0.0, 0.0, 0.0
    p = n_refused / n_total
    denom = 1 + z**2 / n_total
    center = (p + z**2 / (2 * n_total)) / denom
    margin = z * np.sqrt(p * (1 - p) / n_total + z**2 / (4 * n_total**2)) / denom
    return center, max(0.0, center - margin), min(1.0, center + margin)


def _compute_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-(display_name, provider, tier) Wilson refusal-rate stats.

    Strict refusal = direct_refusal | indirect_refusal.

    Parameters
    ----------
    df:
        Raw adjudicated.csv DataFrame with columns
        [model, modal_compliance, tier, subdomain, ...].

    Returns
    -------
    DataFrame with columns:
        model, provider, tier, n, n_refused, refusal_rate, ci_lo, ci_hi
    """
    df = df.copy()
    df["display"] = df["model"].map(lambda m: _MODEL_META.get(m, (m, "other"))[0])
    df["provider"] = df["model"].map(lambda m: _MODEL_META.get(m, (m, "other"))[1])
    df["is_refused"] = df["modal_compliance"].isin(["direct_refusal", "indirect_refusal"])

    rows = []
    for (display, provider, tier), grp in df.groupby(["display", "provider", "tier"]):
        n = len(grp)
        n_refused = int(grp["is_refused"].sum())
        rate, lo, hi = _wilson_ci(n_refused, n)
        rows.append(
            {
                "model": display,
                "provider": provider,
                "tier": tier,
                "n": n,
                "n_refused": n_refused,
                "raw_rate": n_refused / n if n > 0 else 0.0,
                "refusal_rate": rate,
                "ci_lo": lo,
                "ci_hi": hi,
            }
        )
    return pd.DataFrame(rows)


def _overall_order(stats_df: pd.DataFrame) -> list[str]:
    """Return display names sorted by overall refusal rate, descending."""
    overall = (
        stats_df.groupby("model")[["n_refused", "n"]]
        .sum()
        .apply(lambda r: r["n_refused"] / r["n"], axis=1)
        .sort_values(ascending=False)
    )
    return [str(m) for m in overall.index]


# ---------------------------------------------------------------------------
# Figure 1 — Provider gradient (benign-tier refusal rates, all 19 models)
# ---------------------------------------------------------------------------


def figure1_provider_gradient(
    df: pd.DataFrame,
    *,
    model_col: str = "model",
    provider_col: str = "provider",
    rate_col: str = "refusal_rate",
    ci_lo_col: str = "ci_lo",
    ci_hi_col: str = "ci_hi",
    tier: str = "benign",
    tier_col: str | None = "tier",
) -> plt.Figure:  # type: ignore[name-defined]
    """Figure 1: Refusal rate by model (benign prompts), coloured by provider.

    Models are sorted by refusal rate descending.

    Parameters
    ----------
    df:
        DataFrame from :func:`_compute_stats` with columns
        [model, provider, tier, refusal_rate, ci_lo, ci_hi].

    Returns
    -------
    matplotlib Figure

    Example
    -------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     "model": ["claude-opus-4-7", "mistral-large"],
    ...     "provider": ["anthropic", "mistral"],
    ...     "tier": ["benign", "benign"],
    ...     "refusal_rate": [0.7, 0.0],
    ...     "ci_lo": [0.5, 0.0],
    ...     "ci_hi": [0.85, 0.0],
    ... })
    >>> fig = figure1_provider_gradient(df)
    >>> fig is not None
    True
    """
    if tier_col and tier_col in df.columns:
        df = df[df[tier_col] == tier].copy()

    # Sort by refusal rate descending
    df = df.sort_values(rate_col, ascending=False).reset_index(drop=True)
    colors = [_provider_color(p) for p in df[provider_col]]

    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(df))
    ax.bar(x, df[rate_col], color=colors, alpha=0.85, zorder=3, width=0.7)
    if ci_lo_col in df.columns and ci_hi_col in df.columns:
        ax.errorbar(
            x,
            df[rate_col],
            yerr=[df[rate_col] - df[ci_lo_col], df[ci_hi_col] - df[rate_col]],
            fmt="none",
            color="black",
            capsize=4,
            linewidth=1.2,
            zorder=4,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(df[model_col], rotation=40, ha="right", fontsize=9)
    ax.set_ylabel("Refusal rate (benign prompts)")
    ax.set_ylim(0, 1.08)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    ax.set_title("Provider gradient: refusal rate on benign protein-design prompts")

    # Legend — one patch per provider (deduplicated, preserve order)
    seen: dict[str, str] = {}
    for provider, color in zip(df[provider_col], colors, strict=False):
        if provider not in seen:
            seen[provider] = color
    patches = [mpatches.Patch(color=c, label=p.upper()) for p, c in seen.items()]
    ax.legend(handles=patches, loc="upper right", fontsize=8, ncol=2)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Figure 2 — Subdomain heatmap (model × subdomain)
# ---------------------------------------------------------------------------


def figure2_subdomain_heatmap(
    df: pd.DataFrame,
    *,
    model_col: str = "model",
    subdomain_col: str = "subdomain",
    rate_col: str = "refusal_rate",
    model_order: list[str] | None = None,
) -> plt.Figure:  # type: ignore[name-defined]
    """Figure 2: Refusal rate heatmap across (model × subdomain).

    Example
    -------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     "model": ["opus", "opus", "mistral", "mistral"],
    ...     "subdomain": ["binder_design", "de_novo_protein"] * 2,
    ...     "refusal_rate": [0.7, 0.0, 0.0, 0.0],
    ... })
    >>> fig = figure2_subdomain_heatmap(df)
    >>> fig is not None
    True
    """
    pivot = df.pivot_table(index=model_col, columns=subdomain_col, values=rate_col, aggfunc="mean")
    if model_order:
        pivot = pivot.reindex([m for m in model_order if m in pivot.index])

    fig, ax = plt.subplots(figsize=(13, max(5, len(pivot) * 0.55)))
    im = ax.imshow(pivot.values, aspect="auto", cmap="YlOrRd", vmin=0, vmax=1)
    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_xticklabels(
        [c.replace("_", " ") for c in pivot.columns],
        rotation=40,
        ha="right",
        fontsize=9,
    )
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=9)

    # Annotate cells with rate value
    for row_i in range(len(pivot.index)):
        for col_i in range(len(pivot.columns)):
            val = pivot.values[row_i, col_i]
            if not np.isnan(val):
                ax.text(
                    col_i,
                    row_i,
                    f"{val:.0%}",
                    ha="center",
                    va="center",
                    fontsize=6.5,
                    color="white" if val > 0.55 else "black",
                )

    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("Refusal rate (strict)", fontsize=9)
    cbar.ax.tick_params(labelsize=8)
    ax.set_title("Refusal rate by model and protein-design subdomain")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Figure 3 — Opus longitudinal (per-tier lines: 4.5 → 4.6 → 4.7)
# ---------------------------------------------------------------------------


def figure3_opus_longitudinal(
    df: pd.DataFrame,
    opus_models: list[str] | None = None,
    *,
    model_col: str = "model",
    rate_col: str = "refusal_rate",
    ci_lo_col: str = "ci_lo",
    ci_hi_col: str = "ci_hi",
    tier_col: str = "tier",
    raw_rate_col: str = "raw_rate",
) -> plt.Figure:  # type: ignore[name-defined]
    """Figure 3: Per-tier refusal trajectory across Opus 4.5 / 4.6 / 4.7.

    Draws three lines — benign (green), borderline (amber), dual-use (red) —
    with shaded 95 % Wilson CI bands.

    Point labels use raw_rate (n_refused/n) so that 235/235 annotates as
    "100%" rather than the Wilson center "99%".

    Example
    -------
    >>> import pandas as pd
    >>> rows = []
    >>> for m in ["Opus 4.5", "Opus 4.6", "Opus 4.7"]:
    ...     for t in ["benign", "borderline", "dual_use"]:
    ...         rows.append({"model": m, "tier": t,
    ...                      "refusal_rate": 0.5, "raw_rate": 0.5,
    ...                      "ci_lo": 0.4, "ci_hi": 0.6})
    >>> df = pd.DataFrame(rows)
    >>> fig = figure3_opus_longitudinal(df)
    >>> fig is not None
    True
    """
    if opus_models is None:
        opus_models = ["Opus 4.5", "Opus 4.6", "Opus 4.7"]

    x = np.arange(len(opus_models))
    x_labels = opus_models

    fig, ax = plt.subplots(figsize=(7, 4.5))

    for tier in _TIERS:
        sub = df[df[tier_col] == tier].set_index(model_col).reindex(opus_models)
        rates = np.asarray(sub[rate_col], dtype=float)
        # Use raw rate for labels; fall back to Wilson center if column absent
        if raw_rate_col in sub.columns:
            label_rates = np.asarray(sub[raw_rate_col], dtype=float)
        else:
            label_rates = rates
        color = _TIER_COLORS[tier]
        label = _TIER_LABELS[tier]
        ax.plot(x, rates, marker="o", color=color, linewidth=2, label=label, zorder=3)
        if ci_lo_col in sub.columns and ci_hi_col in sub.columns:
            lo = np.asarray(sub[ci_lo_col], dtype=float)
            hi = np.asarray(sub[ci_hi_col], dtype=float)
            ax.fill_between(x, lo, hi, alpha=0.15, color=color, zorder=2)
        # Annotate using raw rate so 235/235 → "100%", not Wilson centre "99%"
        for xi, lrate in zip(x, label_rates, strict=True):
            if not np.isnan(lrate):
                ax.annotate(
                    f"{round(lrate * 100):.0f}%",
                    (float(xi), float(rates[xi])),
                    textcoords="offset points",
                    xytext=(0, 7),
                    ha="center",
                    fontsize=8,
                    color=color,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, fontsize=10)
    ax.set_ylabel("Strict refusal rate")
    ax.set_ylim(-0.05, 1.15)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(title="Tier", loc="center left", bbox_to_anchor=(1.01, 0.5))
    ax.set_title("Longitudinal refusal trajectory: Opus 4.5 / 4.6 / 4.7")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Figure 4 — Refusal taxonomy (stacked bar, top N models by refusal count)
# ---------------------------------------------------------------------------


def figure4_refusal_taxonomy(
    df: pd.DataFrame,
    *,
    model_col: str = "model",
    compliance_col: str = "modal_compliance",
    reason_col: str = "modal_reason",
    top_n_models: int = 5,
) -> plt.Figure:  # type: ignore[name-defined]
    """Figure 4: Stacked bar of MUSE compliance × reason for top refusing models.

    Example
    -------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     "model": ["opus", "opus"],
    ...     "modal_compliance": ["direct_refusal", "direct_refusal"],
    ...     "modal_reason": ["safety_policy", "dual_use_concern"],
    ... })
    >>> fig = figure4_refusal_taxonomy(df)
    >>> fig is not None
    True
    """
    from refusalbench.council import REFUSAL_KEYS

    df = df[df[compliance_col].isin(REFUSAL_KEYS)].copy()
    top_models = df.groupby(model_col).size().nlargest(top_n_models).index.tolist()
    df = df[df[model_col].isin(top_models)]

    pivot = df.groupby([model_col, reason_col]).size().unstack(fill_value=0)
    pivot = pivot.reindex(index=top_models)
    pivot_norm = pivot.div(pivot.sum(axis=1), axis=0)

    fig, ax = plt.subplots(figsize=(10, 5))
    bottom = np.zeros(len(top_models))
    cmap = mpl.colormaps.get_cmap("tab10").resampled(len(pivot_norm.columns))
    for col_i, col in enumerate(pivot_norm.columns):
        vals = np.asarray(pivot_norm[col], dtype=float)
        ax.bar(
            top_models,
            vals,
            bottom=bottom,
            label=col,
            color=cmap(col_i),
            alpha=0.88,
        )
        bottom += vals
    ax.set_ylabel("Fraction of refusals")
    ax.set_ylim(0, 1.05)
    ax.legend(loc="lower right", fontsize=8, ncol=2)
    ax.set_title("Refusal reason taxonomy for highest-refusing models")
    plt.xticks(rotation=20, ha="right", fontsize=9)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Figure 5 — Tier comparison (grouped bar, all 19 models sorted by rate)
# ---------------------------------------------------------------------------


def figure5_tier_comparison(
    df: pd.DataFrame,
    *,
    model_col: str = "model",
    tier_col: str = "tier",
    rate_col: str = "refusal_rate",
    ci_lo_col: str = "ci_lo",
    ci_hi_col: str = "ci_hi",
    model_order: list[str] | None = None,
) -> plt.Figure:  # type: ignore[name-defined]
    """Figure 5: Refusal rate by (model, tier) — benign vs borderline vs dual-use.

    Models sorted by overall refusal rate descending when model_order is None.

    Example
    -------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     "model": ["opus", "opus", "opus"],
    ...     "tier": ["benign", "borderline", "dual_use"],
    ...     "refusal_rate": [0.7, 0.8, 0.9],
    ...     "ci_lo": [0.55, 0.65, 0.78],
    ...     "ci_hi": [0.82, 0.92, 0.97],
    ... })
    >>> fig = figure5_tier_comparison(df)
    >>> fig is not None
    True
    """
    if model_order is None:
        # Sort by overall (mean across tiers) descending
        overall = df.groupby(model_col)[rate_col].mean().sort_values(ascending=False)
        model_order = overall.index.tolist()

    x = np.arange(len(model_order))
    n_tiers = len(_TIERS)
    width = 0.22

    fig, ax = plt.subplots(figsize=(13, 5))
    for i, tier in enumerate(_TIERS):
        sub = df[df[tier_col] == tier].set_index(model_col).reindex(model_order)
        rates = np.asarray(sub[rate_col].fillna(0), dtype=float)
        offset = (i - (n_tiers - 1) / 2) * width
        ax.bar(
            x + offset,
            rates,
            width,
            label=_TIER_LABELS[tier],
            color=_TIER_COLORS[tier],
            alpha=0.88,
        )
        if ci_lo_col in sub.columns and ci_hi_col in sub.columns:
            ci_lo = np.asarray(sub[ci_lo_col].fillna(0), dtype=float)
            ci_hi = np.asarray(sub[ci_hi_col].fillna(0), dtype=float)
            ax.errorbar(
                x + offset,
                rates,
                yerr=[(rates - ci_lo).clip(0), (ci_hi - rates).clip(0)],
                fmt="none",
                color="black",
                capsize=2.5,
                linewidth=0.9,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(model_order, rotation=35, ha="right", fontsize=8.5)
    ax.set_ylabel("Strict refusal rate")
    ax.set_ylim(0, 1.12)
    ax.legend(title="Tier", fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title("Tier-stratified refusal rates: benign vs borderline vs dual-use")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Figure 6 — WMDP-Bio capability vs refusal rate scatter
# ---------------------------------------------------------------------------


def figure6_wmdp_scatter(
    per_model_df: pd.DataFrame,
    wmdp_scores: dict[str, float],
    *,
    model_col: str = "model",
    provider_col: str = "provider",
    rate_col: str = "refusal_rate",
) -> plt.Figure:  # type: ignore[name-defined]
    """Figure 6: WMDP-Bio score vs refusal rate scatter with regression line.

    Example
    -------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     "model": ["opus", "mistral"],
    ...     "provider": ["anthropic", "mistral"],
    ...     "refusal_rate": [0.7, 0.0],
    ... })
    >>> wmdp = {"opus": 0.82, "mistral": 0.74}
    >>> fig = figure6_wmdp_scatter(df, wmdp)
    >>> fig is not None
    True
    """
    df = per_model_df.copy()
    df["wmdp"] = df[model_col].map(wmdp_scores)
    df = df.dropna(subset=["wmdp", rate_col])

    fig, ax = plt.subplots(figsize=(7, 5))
    colors = [_provider_color(p) for p in df.get(provider_col, pd.Series(["other"] * len(df)))]
    ax.scatter(df["wmdp"], df[rate_col], c=colors, s=80, zorder=3)
    for _, row in df.iterrows():
        ax.annotate(
            str(row[model_col]),
            (row["wmdp"], row[rate_col]),
            fontsize=7,
            textcoords="offset points",
            xytext=(5, 3),
        )

    if len(df) >= 2:
        m_coef, b_coef = np.polyfit(df["wmdp"], df[rate_col], 1)
        x_line = np.linspace(float(df["wmdp"].min()), float(df["wmdp"].max()), 50)
        ax.plot(
            x_line,
            m_coef * x_line + b_coef,
            color="black",
            linewidth=1,
            linestyle="--",
            alpha=0.6,
        )

    ax.set_xlabel("WMDP-Bio score")
    ax.set_ylabel("Refusal rate (benign prompts)")
    ax.set_ylim(-0.05, 1.1)
    ax.grid(alpha=0.3)
    ax.set_title("WMDP-Bio capability vs refusal rate (H4)")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Save helper
# ---------------------------------------------------------------------------


def save_figure(fig: Any, name: str, output_dir: Path | None = None) -> None:
    """Save a figure as both PDF (vector) and PNG (300 dpi) to the figures directory.

    Example
    -------
    >>> import matplotlib.pyplot as plt
    >>> fig = plt.figure()
    >>> save_figure(fig, "test_fig")  # saves to results/figures/
    """
    out = output_dir or _FIGURE_DIR
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(out / f"{name}.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# CLI — loads adjudicated.csv and generates all six figures
# ---------------------------------------------------------------------------


@click.command()
@click.option("--all", "all_figs", is_flag=True, help="Regenerate all figures.")
@click.option(
    "--results-dir",
    default="results/snapshots/2026-05",
    show_default=True,
    help="Directory containing council/adjudicated.csv.",
)
@click.option(
    "--output-dir",
    default="results/figures",
    show_default=True,
    help="Output directory for PDF/PNG files.",
)
def main(all_figs: bool, results_dir: str, output_dir: str) -> None:
    """Generate all RefusalBench paper figures from the canonical adjudicated.csv."""
    if not all_figs:
        click.echo("Pass --all to regenerate all figures.")
        return

    results_path = Path(results_dir)
    output_path = Path(output_dir)

    # Locate adjudicated.csv
    candidates = [
        results_path / "council" / "adjudicated.csv",
        results_path / "adjudicated.csv",
    ]
    adj_path = next((p for p in candidates if p.exists()), None)
    if adj_path is None:
        raise click.ClickException(
            f"adjudicated.csv not found under {results_path}. "
            "Tried: " + ", ".join(str(p) for p in candidates)
        )

    click.echo(f"Loading {adj_path} …")
    raw = pd.read_csv(adj_path)
    click.echo(f"  {len(raw):,} rows, {raw['model'].nunique()} models")

    # Compute per-(model, tier) stats
    stats = _compute_stats(raw)

    # Global model order: overall refusal rate descending (matches Table 3.4)
    model_order = _overall_order(stats)

    # ------------------------------------------------------------------
    # Figure 1 — benign gradient
    # ------------------------------------------------------------------
    click.echo("Generating Figure 1 …")
    fig1 = figure1_provider_gradient(stats, tier="benign")
    save_figure(fig1, "figure1_provider_gradient", output_path)

    # ------------------------------------------------------------------
    # Figure 2 — subdomain heatmap
    # ------------------------------------------------------------------
    click.echo("Generating Figure 2 …")
    raw2 = raw.copy()
    raw2["display"] = raw2["model"].map(lambda m: _MODEL_META.get(m, (m, "other"))[0])
    raw2["is_refused"] = raw2["modal_compliance"].isin(["direct_refusal", "indirect_refusal"])
    sub_heat = (
        raw2.groupby(["display", "subdomain"])["is_refused"]
        .mean()
        .reset_index()
        .rename(columns={"display": "model", "is_refused": "refusal_rate"})
    )
    fig2 = figure2_subdomain_heatmap(sub_heat, model_order=model_order)
    save_figure(fig2, "figure2_subdomain_heatmap", output_path)

    # ------------------------------------------------------------------
    # Figure 3 — Opus longitudinal (per-tier)
    # ------------------------------------------------------------------
    click.echo("Generating Figure 3 …")
    opus_labels = ["Opus 4.5", "Opus 4.6", "Opus 4.7"]
    opus_stats = stats[stats["model"].isin(opus_labels)].copy()
    fig3 = figure3_opus_longitudinal(
        opus_stats,
        opus_models=opus_labels,
    )
    save_figure(fig3, "figure3_opus_longitudinal", output_path)

    # ------------------------------------------------------------------
    # Figure 4 — refusal taxonomy (raw rows needed)
    # ------------------------------------------------------------------
    click.echo("Generating Figure 4 …")
    raw4 = raw.copy()
    raw4["model"] = raw4["model"].map(lambda m: _MODEL_META.get(m, (m, "other"))[0])
    try:
        fig4 = figure4_refusal_taxonomy(raw4, top_n_models=6)
        save_figure(fig4, "figure4_refusal_taxonomy", output_path)
    except Exception as exc:
        click.echo(f"  Figure 4 skipped ({exc})")

    # ------------------------------------------------------------------
    # Figure 5 — tier comparison
    # ------------------------------------------------------------------
    click.echo("Generating Figure 5 …")
    fig5 = figure5_tier_comparison(stats, model_order=model_order)
    save_figure(fig5, "figure5_tier_comparison", output_path)

    # ------------------------------------------------------------------
    # Figure 6 — WMDP scatter (requires external scores; skipped if absent)
    # ------------------------------------------------------------------
    wmdp_path = results_path / "wmdp_scores.csv"
    if wmdp_path.exists():
        click.echo("Generating Figure 6 …")
        wmdp_df = pd.read_csv(wmdp_path)
        wmdp_scores = dict(zip(wmdp_df["model"], wmdp_df["score"], strict=True))
        benign_stats = stats[stats["tier"] == "benign"].copy()
        fig6 = figure6_wmdp_scatter(benign_stats, wmdp_scores)
        save_figure(fig6, "figure6_wmdp_scatter", output_path)
    else:
        click.echo("  Figure 6 skipped — wmdp_scores.csv not found.")

    click.echo(f"\nDone. Figures written to {output_path.resolve()}")


if __name__ == "__main__":
    main()
