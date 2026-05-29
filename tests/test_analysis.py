"""Tests for analysis/figures.py and analysis/stats.py."""

from __future__ import annotations

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Figures smoke tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def provider_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "model": ["claude-opus-4-7", "claude-sonnet-4-6", "mistral-large", "deepseek-v3"],
            "provider": ["anthropic", "anthropic", "mistral", "deepseek"],
            "tier": ["benign"] * 4,
            "refusal_rate": [0.7, 0.13, 0.0, 0.0],
            "ci_lo": [0.55, 0.05, 0.0, 0.0],
            "ci_hi": [0.82, 0.25, 0.0, 0.0],
        }
    )


@pytest.fixture()
def subdomain_df() -> pd.DataFrame:
    models = ["opus", "mistral"]
    subdomains = ["binder_design", "de_novo_protein", "enzyme_design"]
    rows = [
        {"model": m, "subdomain": s, "refusal_rate": 0.5 if m == "opus" else 0.0}
        for m in models
        for s in subdomains
    ]
    return pd.DataFrame(rows)


@pytest.fixture()
def opus_df() -> pd.DataFrame:
    # figure3 draws one line per tier, so the frame needs a `tier` column.
    rows = []
    for model in ("Opus 4.5", "Opus 4.6", "Opus 4.7"):
        for tier in ("benign", "borderline", "dual_use"):
            rows.append(
                {
                    "model": model,
                    "tier": tier,
                    "refusal_rate": 0.6,
                    "raw_rate": 0.6,
                    "ci_lo": 0.45,
                    "ci_hi": 0.75,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture()
def taxonomy_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "model": ["opus"] * 6,
            "modal_compliance": ["direct_refusal"] * 6,
            "modal_reason": [
                "safety_policy",
                "dual_use_concern",
                "biosecurity_concern",
                "safety_policy",
                "dual_use_concern",
                "safety_policy",
            ],
        }
    )


@pytest.fixture()
def tier_df() -> pd.DataFrame:
    rows = []
    for tier in ("benign", "borderline", "dual_use"):
        for model in ("opus", "mistral"):
            rows.append(
                {
                    "model": model,
                    "tier": tier,
                    "refusal_rate": 0.7 if model == "opus" else 0.0,
                    "ci_lo": 0.5 if model == "opus" else 0.0,
                    "ci_hi": 0.85 if model == "opus" else 0.0,
                }
            )
    return pd.DataFrame(rows)


def test_figure1_returns_figure(provider_df: pd.DataFrame) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from refusalbench.analysis.figures import figure1_provider_gradient

    fig = figure1_provider_gradient(provider_df)
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_figure2_returns_figure(subdomain_df: pd.DataFrame) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from refusalbench.analysis.figures import figure2_subdomain_heatmap

    fig = figure2_subdomain_heatmap(subdomain_df)
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_figure3_returns_figure(opus_df: pd.DataFrame) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from refusalbench.analysis.figures import figure3_opus_longitudinal

    fig = figure3_opus_longitudinal(opus_df)
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_figure4_returns_figure(taxonomy_df: pd.DataFrame) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from refusalbench.analysis.figures import figure4_refusal_taxonomy

    fig = figure4_refusal_taxonomy(taxonomy_df)
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_figure5_returns_figure(tier_df: pd.DataFrame) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from refusalbench.analysis.figures import figure5_tier_comparison

    fig = figure5_tier_comparison(tier_df)
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_figure6_returns_figure(provider_df: pd.DataFrame) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from refusalbench.analysis.figures import figure6_wmdp_scatter

    wmdp = {"claude-opus-4-7": 0.82, "mistral-large": 0.74}
    fig = figure6_wmdp_scatter(provider_df, wmdp)
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_save_figure_creates_files(tmp_path: pytest.TempPathFixture, opus_df: pd.DataFrame) -> None:  # type: ignore[name-defined]
    import matplotlib

    matplotlib.use("Agg")
    from refusalbench.analysis.figures import figure3_opus_longitudinal, save_figure

    fig = figure3_opus_longitudinal(opus_df)
    save_figure(fig, "test_fig", output_dir=tmp_path)
    assert (tmp_path / "test_fig.pdf").exists()
    assert (tmp_path / "test_fig.png").exists()


# ---------------------------------------------------------------------------
# Stats smoke tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def results_df() -> pd.DataFrame:
    """Minimal results DataFrame with providers, subdomains, and jurisdictions."""
    rows = []
    for provider, model, jurisdiction in [
        ("anthropic", "opus", "us"),
        ("mistral", "mistral-large", "eu"),
        ("deepseek", "ds-v3", "asia"),
    ]:
        for subdomain in ("binder_design", "de_novo_protein"):
            for i in range(8):
                rows.append(
                    {
                        "model": model,
                        "provider": provider,
                        "jurisdiction": jurisdiction,
                        "subdomain": subdomain,
                        "prompt_id": f"p{i}",
                        "trial_idx": 0,
                        "tier": "benign",
                        "modal_compliance": (
                            "direct_refusal"
                            if (provider == "anthropic" and subdomain == "binder_design")
                            else "compliance"
                        ),
                    }
                )
    return pd.DataFrame(rows)


# --- H1: jurisdictional clustering ---


def test_h1_jurisdictional_clustering_returns_expected_keys(results_df: pd.DataFrame) -> None:
    from refusalbench.analysis.stats import h1_jurisdictional_clustering

    result = h1_jurisdictional_clustering(results_df)
    assert result["hypothesis"] == "H1"
    assert "kruskal_h" in result
    assert "kruskal_p" in result
    assert "eta_squared" in result
    assert "per_jurisdiction_rates" in result
    assert "n_models" in result


def test_h1_per_jurisdiction_rates_present(results_df: pd.DataFrame) -> None:
    from refusalbench.analysis.stats import h1_jurisdictional_clustering

    result = h1_jurisdictional_clustering(results_df)
    rates = result["per_jurisdiction_rates"]
    assert set(rates.keys()) == {"us", "eu", "asia"}


def test_h1_insufficient_jurisdictions() -> None:
    import math

    from refusalbench.analysis.stats import h1_jurisdictional_clustering

    df = pd.DataFrame(
        {
            "modal_compliance": ["direct_refusal", "compliance"],
            "model": ["opus", "sonnet"],
            "jurisdiction": ["us", "us"],
            "tier": ["benign", "benign"],
        }
    )
    result = h1_jurisdictional_clustering(df)
    assert result["hypothesis"] == "H1"
    assert math.isnan(result["kruskal_p"])


# --- H2: provider gradient (was old H1) ---


def test_h2_returns_expected_keys(results_df: pd.DataFrame) -> None:
    from refusalbench.analysis.stats import h2_provider_clustering

    result = h2_provider_clustering(results_df)
    assert result["hypothesis"] == "H2"
    assert "p_value" in result
    assert "or_anthropic" in result
    assert "n_observations" in result


def test_h2_counts_observations(results_df: pd.DataFrame) -> None:
    from refusalbench.analysis.stats import h2_provider_clustering

    result = h2_provider_clustering(results_df)
    assert result["n_observations"] == len(results_df)


def test_h2_backward_compat_alias(results_df: pd.DataFrame) -> None:
    from refusalbench.analysis.stats import h1_provider_logistic, h2_provider_clustering

    r1 = h1_provider_logistic(results_df)
    r2 = h2_provider_clustering(results_df)
    assert r1["hypothesis"] == r2["hypothesis"] == "H2"


# --- H3: subdomain specificity within Anthropic (was old H2) ---


def test_h3_returns_expected_keys(results_df: pd.DataFrame) -> None:
    from refusalbench.analysis.stats import h3_subdomain_anthropic

    result = h3_subdomain_anthropic(results_df)
    assert result["hypothesis"] == "H3"
    assert "p_value" in result
    assert "or_binder_vs_denovo" in result


def test_h3_empty_when_no_anthropic() -> None:
    import math

    from refusalbench.analysis.stats import h3_subdomain_anthropic

    df = pd.DataFrame(
        {
            "modal_compliance": ["compliance"],
            "provider": ["mistral"],
            "subdomain": ["binder_design"],
            "prompt_id": ["p1"],
        }
    )
    result = h3_subdomain_anthropic(df)
    assert result["n_observations"] == 0
    assert math.isnan(result["p_value"])


def test_h3_backward_compat_alias(results_df: pd.DataFrame) -> None:
    from refusalbench.analysis.stats import h2_subdomain_anthropic, h3_subdomain_anthropic

    r1 = h2_subdomain_anthropic(results_df)
    r2 = h3_subdomain_anthropic(results_df)
    assert r1["hypothesis"] == r2["hypothesis"] == "H3"


# --- H4: longitudinal Opus trajectory (was old H3) ---


def test_h4_returns_direction() -> None:
    from refusalbench.analysis.stats import h4_opus_longitudinal

    df = pd.DataFrame(
        {
            "modal_compliance": [
                "direct_refusal",
                "direct_refusal",
                "compliance",
                "compliance",
                "compliance",
                "compliance",
            ],
            "model": [
                "claude-opus-4-5",
                "claude-opus-4-5",
                "claude-opus-4-6",
                "claude-opus-4-6",
                "claude-opus-4-7",
                "claude-opus-4-7",
            ],
            "prompt_id": ["p1", "p2"] * 3,
        }
    )
    result = h4_opus_longitudinal(df)
    assert "direction" in result
    assert result["hypothesis"] == "H4"


def test_h4_insufficient_data() -> None:
    from refusalbench.analysis.stats import h4_opus_longitudinal

    df = pd.DataFrame(
        {
            "modal_compliance": ["direct_refusal"],
            "model": ["claude-opus-4-5"],
            "prompt_id": ["p1"],
        }
    )
    result = h4_opus_longitudinal(df)
    assert result["direction"] == "insufficient_data"


def test_h4_backward_compat_alias() -> None:
    from refusalbench.analysis.stats import h3_opus_longitudinal, h4_opus_longitudinal

    df = pd.DataFrame(
        {
            "modal_compliance": [
                "direct_refusal",
                "compliance",
                "compliance",
                "compliance",
                "compliance",
                "compliance",
            ],
            "model": ["claude-opus-4-5"] * 2 + ["claude-opus-4-6"] * 2 + ["claude-opus-4-7"] * 2,
            "prompt_id": ["p1", "p2"] * 3,
        }
    )
    r1 = h3_opus_longitudinal(df)
    r2 = h4_opus_longitudinal(df)
    assert r1["hypothesis"] == r2["hypothesis"] == "H4"


# --- H5: capability decoupling (was old H4) ---


def test_h5_returns_spearman_rho() -> None:
    from refusalbench.analysis.stats import h5_capability_correlation

    df = pd.DataFrame(
        {
            "model": ["opus", "mistral", "deepseek", "qwen"],
            "modal_compliance": ["direct_refusal", "compliance", "compliance", "compliance"],
            "provider": ["anthropic", "mistral", "deepseek", "qwen"],
        }
    )
    wmdp = {"opus": 0.82, "mistral": 0.74, "deepseek": 0.71, "qwen": 0.68}
    result = h5_capability_correlation(df, wmdp)
    assert "spearman_rho" in result
    assert result["hypothesis"] == "H5"


def test_h5_insufficient_data() -> None:
    from refusalbench.analysis.stats import h5_capability_correlation

    df = pd.DataFrame(
        {"model": ["opus"], "modal_compliance": ["direct_refusal"], "provider": ["anthropic"]}
    )
    result = h5_capability_correlation(df, {"opus": 0.82})
    assert result["hypothesis"] == "H5"


def test_h5_backward_compat_alias() -> None:
    from refusalbench.analysis.stats import h4_capability_correlation, h5_capability_correlation

    df = pd.DataFrame(
        {
            "model": ["opus", "mistral", "deepseek", "qwen"],
            "modal_compliance": ["direct_refusal", "compliance", "compliance", "compliance"],
            "provider": ["anthropic", "mistral", "deepseek", "qwen"],
        }
    )
    wmdp = {"opus": 0.82, "mistral": 0.74, "deepseek": 0.71, "qwen": 0.68}
    r1 = h4_capability_correlation(df, wmdp)
    r2 = h5_capability_correlation(df, wmdp)
    assert r1["hypothesis"] == r2["hypothesis"] == "H5"
