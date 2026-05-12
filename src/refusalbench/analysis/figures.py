"""Six publication-quality figures for the RefusalBench paper.

All functions read from DataFrames (no direct file I/O) and return a
matplotlib Figure. The CLI entry point saves PDF + PNG.

Run all: ``python -m refusalbench.analysis.figures --all``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_PROVIDER_COLORS: dict[str, str] = {
    "anthropic": "#E53E3E",
    "mistral": "#3182CE",
    "deepseek": "#38A169",
    "qwen": "#D69E2E",
    "meta": "#805AD5",
    "zhipu": "#319795",
    "other": "#718096",
}

_FIGURE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "results" / "figures"


def _provider_color(provider: str) -> str:
    return _PROVIDER_COLORS.get(provider.lower(), _PROVIDER_COLORS["other"])


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
    """Figure 1: Refusal rate by model, grouped by provider, benign prompts.

    Parameters
    ----------
    df:
        DataFrame from :func:`refusalbench.score.refusal_rates_by_group`
        with columns [model, provider, tier, refusal_rate, ci_lo, ci_hi].

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
        df = df[df[tier_col] == tier]

    df = df.sort_values([provider_col, model_col])
    colors = [_provider_color(p) for p in df[provider_col]]

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(df))
    ax.bar(x, df[rate_col], color=colors, alpha=0.85, zorder=3)
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
    ax.set_ylabel("Refusal rate (benign prompts)", fontsize=11)
    ax.set_ylim(0, 1.05)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    ax.set_title("Provider gradient: refusal rate on benign protein-design prompts", fontsize=12)

    # Legend patches
    seen: set[str] = set()
    patches = []
    for provider, color in zip(df[provider_col], colors, strict=False):
        if provider not in seen:
            patches.append(plt.matplotlib.patches.Patch(color=color, label=provider))  # type: ignore[attr-defined]
            seen.add(provider)
    ax.legend(handles=patches, loc="upper right", fontsize=9)
    fig.tight_layout()
    return fig


def figure2_subdomain_heatmap(
    df: pd.DataFrame,
    *,
    model_col: str = "model",
    subdomain_col: str = "subdomain",
    rate_col: str = "refusal_rate",
) -> plt.Figure:  # type: ignore[name-defined]
    """Figure 2: Refusal rate heatmap across (model x subdomain).

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
    fig, ax = plt.subplots(figsize=(12, max(4, len(pivot) * 0.6)))
    im = ax.imshow(pivot.values, aspect="auto", cmap="YlOrRd", vmin=0, vmax=1)
    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=40, ha="right", fontsize=9)
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=9)
    plt.colorbar(im, ax=ax, label="Refusal rate")
    ax.set_title("Refusal rate by model and protein-design subdomain", fontsize=12)
    fig.tight_layout()
    return fig


def figure3_opus_longitudinal(
    df: pd.DataFrame,
    opus_models: list[str] | None = None,
    *,
    model_col: str = "model",
    rate_col: str = "refusal_rate",
    ci_lo_col: str = "ci_lo",
    ci_hi_col: str = "ci_hi",
) -> plt.Figure:  # type: ignore[name-defined]
    """Figure 3: Refusal rate trajectory across Opus 4.5 -> 4.6 -> 4.7.

    Example
    -------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     "model": ["claude-opus-4-5", "claude-opus-4-6", "claude-opus-4-7"],
    ...     "refusal_rate": [0.6, 0.4, 0.7],
    ...     "ci_lo": [0.4, 0.25, 0.55],
    ...     "ci_hi": [0.75, 0.55, 0.82],
    ... })
    >>> fig = figure3_opus_longitudinal(df)
    >>> fig is not None
    True
    """
    if opus_models is None:
        opus_models = ["claude-opus-4-5", "claude-opus-4-6", "claude-opus-4-7"]

    sub = df[df[model_col].isin(opus_models)].set_index(model_col)
    sub = sub.reindex(opus_models)
    x = np.arange(len(opus_models))

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(
        x, np.asarray(sub[rate_col]), marker="o", color=_PROVIDER_COLORS["anthropic"], linewidth=2
    )
    if ci_lo_col in sub.columns and ci_hi_col in sub.columns:
        ax.fill_between(
            x,
            np.asarray(sub[ci_lo_col]),
            np.asarray(sub[ci_hi_col]),
            alpha=0.2,
            color=_PROVIDER_COLORS["anthropic"],
        )
    ax.set_xticks(x)
    ax.set_xticklabels(opus_models, fontsize=10)
    ax.set_ylabel("Refusal rate", fontsize=11)
    ax.set_ylim(0, 1.05)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title("Longitudinal refusal trajectory: Opus 4.5 / 4.6 / 4.7", fontsize=12)
    fig.tight_layout()
    return fig


def figure4_refusal_taxonomy(
    df: pd.DataFrame,
    *,
    model_col: str = "model",
    compliance_col: str = "modal_compliance",
    reason_col: str = "modal_reason",
    top_n_models: int = 5,
) -> plt.Figure:  # type: ignore[name-defined]
    """Figure 4: Stacked bar of MUSE compliance x reason for top refusing models.

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
    for col in pivot_norm.columns:
        ax.bar(top_models, pivot_norm[col], bottom=bottom, label=col)
        bottom += np.asarray(pivot_norm[col], dtype=float)
    ax.set_ylabel("Fraction of refusals", fontsize=11)
    ax.set_ylim(0, 1.05)
    ax.legend(loc="lower right", fontsize=8, ncol=2)
    ax.set_title("Refusal reason taxonomy for highest-refusing models", fontsize=12)
    plt.xticks(rotation=20, ha="right", fontsize=9)
    fig.tight_layout()
    return fig


def figure5_tier_comparison(
    df: pd.DataFrame,
    *,
    model_col: str = "model",
    tier_col: str = "tier",
    rate_col: str = "refusal_rate",
    ci_lo_col: str = "ci_lo",
    ci_hi_col: str = "ci_hi",
) -> plt.Figure:  # type: ignore[name-defined]
    """Figure 5: Refusal rate by (model, tier) — benign vs borderline vs dual_use.

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
    tiers = ["benign", "borderline", "dual_use"]
    models = sorted(df[model_col].unique())
    x = np.arange(len(models))
    width = 0.25
    tier_colors = {"benign": "#68D391", "borderline": "#F6AD55", "dual_use": "#FC8181"}

    fig, ax = plt.subplots(figsize=(11, 5))
    for i, tier in enumerate(tiers):
        sub = df[df[tier_col] == tier].set_index(model_col).reindex(models)
        rates = np.asarray(sub[rate_col].fillna(0), dtype=float)
        offset = (i - 1) * width
        ax.bar(x + offset, rates, width, label=tier, color=tier_colors[tier], alpha=0.85)
        if ci_lo_col in sub.columns and ci_hi_col in sub.columns:
            ci_lo = np.asarray(sub[ci_lo_col].fillna(0), dtype=float)
            ci_hi = np.asarray(sub[ci_hi_col].fillna(0), dtype=float)
            ax.errorbar(
                x + offset,
                rates,
                yerr=[
                    (rates - ci_lo).clip(0),
                    (ci_hi - rates).clip(0),
                ],
                fmt="none",
                color="black",
                capsize=3,
                linewidth=1,
            )
    ax.set_xticks(x)
    ax.set_xticklabels(models, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("Refusal rate", fontsize=11)
    ax.set_ylim(0, 1.1)
    ax.legend(title="Tier", fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title("Tier-stratified refusal rates: benign vs borderline vs dual-use", fontsize=12)
    fig.tight_layout()
    return fig


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
    colors = [_provider_color(p) for p in df.get(provider_col, ["other"] * len(df))]
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

    ax.set_xlabel("WMDP-Bio score", fontsize=11)
    ax.set_ylabel("Refusal rate (benign prompts)", fontsize=11)
    ax.set_ylim(-0.05, 1.1)
    ax.grid(alpha=0.3)
    ax.set_title("WMDP-Bio capability vs refusal rate (H4)", fontsize=12)
    fig.tight_layout()
    return fig


def save_figure(fig: Any, name: str, output_dir: Path | None = None) -> None:
    """Save a figure as both PDF and PNG to the figures directory.

    Example
    -------
    >>> import matplotlib.pyplot as plt
    >>> fig = plt.figure()
    >>> save_figure(fig, "test_fig")  # saves to results/figures/
    """
    out = output_dir or _FIGURE_DIR
    out.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(out / f"{name}.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)


@click.command()
@click.option("--all", "all_figs", is_flag=True, help="Regenerate all figures from CSV.")
@click.option("--results-dir", default="results/pretest", show_default=True)
@click.option("--output-dir", default="results/figures", show_default=True)
def main(all_figs: bool, results_dir: str, output_dir: str) -> None:
    """Generate all RefusalBench paper figures from committed CSVs."""
    if not all_figs:
        click.echo("Pass --all to regenerate all figures.")
        return
    click.echo(f"Would generate figures from {results_dir} -> {output_dir}")
    click.echo("(Full implementation runs after sweep data exists.)")


if __name__ == "__main__":
    main()
