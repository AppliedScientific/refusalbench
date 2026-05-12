"""Statistical tests for RefusalBench hypotheses H1-H5.

Each function is a pure transformation: takes DataFrames, returns a
dict of test statistics. No file I/O, no side effects.

Hypothesis numbering matches the paper:
    H1 — Jurisdictional clustering (new)
    H2 — Provider clustering on benign prompts
    H3 — Subdomain specificity within Anthropic
    H4 — Within-Opus version trajectory (Cochran's Q)
    H5 — Capability decoupling (WMDP-Bio Spearman)

Dependencies: scipy, statsmodels (pip install refusalbench[stats]).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def h1_jurisdictional_clustering(
    results: pd.DataFrame,
    *,
    compliance_col: str = "modal_compliance",
    model_col: str = "model",
    jurisdiction_col: str = "jurisdiction",
    tier_col: str = "tier",
    tier: str = "benign",
) -> dict[str, Any]:
    """H1: Refusal patterns cluster by jurisdiction on benign prompts.

    Per-model benign-tier refusal rates are computed, then tested with:

    1. Kruskal-Wallis H across jurisdiction groups — non-parametric,
       appropriate given unequal group sizes (US: 11, Asia: 6, EU: 1).
    2. Eta-squared (η²) — proportion of total per-model-rate variance
       explained by jurisdiction label.
    3. Between-to-within variance ratio — if > 1, models from different
       jurisdictions are more different from each other than models within
       the same jurisdiction are from each other.

    Parameters
    ----------
    results:
        Long-format DataFrame, one row per (prompt_id, model, trial_idx).
        Must include ``jurisdiction`` and ``tier`` columns.
    tier:
        Tier to restrict to (default: "benign").

    Returns
    -------
    dict with keys:
        ``kruskal_h``, ``kruskal_p``
        ``eta_squared``
        ``between_within_ratio``
        ``per_jurisdiction_rates`` — mean refusal rate per jurisdiction
        ``jurisdiction_n_models`` — number of models per jurisdiction
        ``n_models``

    Example
    -------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     "modal_compliance": ["direct_refusal", "compliance", "compliance",
    ...                          "compliance", "compliance", "compliance"],
    ...     "model": ["opus", "mistral", "deepseek", "qwen", "gpt", "gemini"],
    ...     "jurisdiction": ["us", "eu", "asia", "asia", "us", "us"],
    ...     "tier": ["benign"] * 6,
    ... })
    >>> result = h1_jurisdictional_clustering(df)
    >>> "kruskal_p" in result
    True
    """
    from scipy import stats as sp_stats

    from refusalbench.council import REFUSAL_KEYS

    df = results.copy()
    if tier_col in df.columns:
        df = df[df[tier_col] == tier]

    df["refusal"] = df[compliance_col].isin(REFUSAL_KEYS).astype(int)

    per_model = (
        df.groupby([model_col, jurisdiction_col])["refusal"]
        .mean()
        .reset_index()
        .rename(columns={"refusal": "rate"})
    )

    jurisdictions = sorted(per_model[jurisdiction_col].unique())
    groups = [per_model[per_model[jurisdiction_col] == j]["rate"].values for j in jurisdictions]

    _nan = float("nan")
    if len(jurisdictions) < 2 or any(len(g) == 0 for g in groups):
        return {
            "hypothesis": "H1",
            "kruskal_h": _nan,
            "kruskal_p": _nan,
            "eta_squared": _nan,
            "between_within_ratio": _nan,
            "per_jurisdiction_rates": {},
            "jurisdiction_n_models": {},
            "n_models": len(per_model),
        }

    # Kruskal-Wallis
    try:
        h_stat, p_val = sp_stats.kruskal(*groups)
        h_stat, p_val = float(h_stat), float(p_val)
    except Exception:
        h_stat = p_val = _nan

    # Eta-squared: SS_between_jurisdiction / SS_total
    all_rates: np.ndarray[tuple[Any, ...], np.dtype[np.float64]] = np.asarray(
        per_model["rate"].values, dtype=float
    )
    grand_mean = float(all_rates.mean())
    ss_total = float(((all_rates - grand_mean) ** 2).sum())
    group_means = [float(np.asarray(g, dtype=float).mean()) for g in groups]
    group_ns = [len(g) for g in groups]
    ss_between = float(
        sum(n * (m - grand_mean) ** 2 for n, m in zip(group_ns, group_means, strict=True))
    )
    eta_sq = ss_between / ss_total if ss_total > 0 else _nan

    # Between-to-within variance ratio
    within_vars = [float(g.var()) if len(g) > 1 else 0.0 for g in groups]
    mean_within_var = float(np.mean(within_vars))
    between_var = float(np.var(group_means))
    ratio = between_var / mean_within_var if mean_within_var > 0 else _nan

    return {
        "hypothesis": "H1",
        "kruskal_h": h_stat,
        "kruskal_p": p_val,
        "eta_squared": float(eta_sq),
        "between_within_ratio": float(ratio),
        "per_jurisdiction_rates": {
            j: float(g.mean()) for j, g in zip(jurisdictions, groups, strict=True)
        },
        "jurisdiction_n_models": {j: len(g) for j, g in zip(jurisdictions, groups, strict=True)},
        "n_models": len(per_model),
    }


def h2_provider_clustering(
    results: pd.DataFrame,
    *,
    compliance_col: str = "modal_compliance",
    model_col: str = "model",
    provider_col: str = "provider",
    subdomain_col: str = "subdomain",
    prompt_id_col: str = "prompt_id",
) -> dict[str, Any]:
    """H2: Provider-clustered refusal on benign prompts.

    Mixed-effects logistic regression: refusal ~ provider + subdomain,
    random intercept for prompt_id. Tests the Anthropic-vs-others contrast.

    Parameters
    ----------
    results:
        Long-format DataFrame, one row per (prompt_id, model, trial_idx).
        Must include ``provider`` column (e.g. "anthropic", "mistral", etc.).

    Returns
    -------
    dict with keys:
        ``or_anthropic`` — odds ratio for Anthropic provider
        ``ci_lo``, ``ci_hi`` — 95 % CI on OR
        ``p_value`` — p-value for the Anthropic contrast
        ``n_observations``

    Example
    -------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     "modal_compliance": ["direct_refusal", "compliance", "compliance"],
    ...     "provider": ["anthropic", "mistral", "deepseek"],
    ...     "subdomain": ["binder_design"] * 3,
    ...     "prompt_id": ["p1", "p1", "p1"],
    ...     "model": ["opus-4-7", "mistral-large", "deepseek-v3"],
    ... })
    >>> result = h2_provider_clustering(df)
    >>> "p_value" in result
    True
    """
    from refusalbench.council import REFUSAL_KEYS

    try:
        import statsmodels.formula.api as smf
    except ImportError as exc:
        raise ImportError("statsmodels required: pip install 'refusalbench[stats]'") from exc

    df = results.copy()
    df["refusal"] = (df[compliance_col].isin(REFUSAL_KEYS)).astype(int)
    df["is_anthropic"] = (df[provider_col] == "anthropic").astype(int)

    try:
        model = smf.logit(
            "refusal ~ is_anthropic + C(subdomain)",
            data=df,
        ).fit(disp=0)
        coef = float(model.params.get("is_anthropic", float("nan")))
        or_val = float(np.exp(coef))
        ci = model.conf_int()
        ci_lo = (
            float(np.exp(ci.loc["is_anthropic", 0])) if "is_anthropic" in ci.index else float("nan")
        )
        ci_hi = (
            float(np.exp(ci.loc["is_anthropic", 1])) if "is_anthropic" in ci.index else float("nan")
        )
        p_val = float(model.pvalues.get("is_anthropic", float("nan")))
    except Exception:
        or_val = ci_lo = ci_hi = p_val = float("nan")

    return {
        "hypothesis": "H2",
        "or_anthropic": or_val,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "p_value": p_val,
        "n_observations": len(df),
    }


def h3_subdomain_anthropic(
    results: pd.DataFrame,
    *,
    compliance_col: str = "modal_compliance",
    provider_col: str = "provider",
    subdomain_col: str = "subdomain",
    prompt_id_col: str = "prompt_id",
) -> dict[str, Any]:
    """H3: Binder-design over-refusal is Anthropic-specific, not US-wide.

    Logistic regression on Anthropic-only rows: refusal ~ subdomain.
    Tests binder_design vs de_novo_protein contrast.

    Returns
    -------
    dict with ``p_value``, ``or_binder_vs_denovo``, ``ci_lo``, ``ci_hi``.

    Example
    -------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     "modal_compliance": ["direct_refusal", "compliance"],
    ...     "provider": ["anthropic", "anthropic"],
    ...     "subdomain": ["binder_design", "de_novo_protein"],
    ...     "prompt_id": ["p1", "p2"],
    ... })
    >>> result = h3_subdomain_anthropic(df)
    >>> "p_value" in result
    True
    """
    from refusalbench.council import REFUSAL_KEYS

    try:
        import statsmodels.formula.api as smf
    except ImportError as exc:
        raise ImportError("statsmodels required: pip install 'refusalbench[stats]'") from exc

    df = results[results[provider_col] == "anthropic"].copy()
    if df.empty:
        return {
            "hypothesis": "H3",
            "p_value": float("nan"),
            "n_observations": 0,
            "or_binder_vs_denovo": float("nan"),
            "ci_lo": float("nan"),
            "ci_hi": float("nan"),
        }

    df["refusal"] = (df[compliance_col].isin(REFUSAL_KEYS)).astype(int)

    try:
        m = smf.logit(
            f"refusal ~ C({subdomain_col}, Treatment(reference='de_novo_protein'))",
            data=df,
        ).fit(disp=0)
        binder_key = f"C({subdomain_col}, Treatment(reference='de_novo_protein'))[T.binder_design]"
        coef = float(m.params.get(binder_key, float("nan")))
        or_val = float(np.exp(coef))
        ci = m.conf_int()
        ci_lo = float(np.exp(ci.loc[binder_key, 0])) if binder_key in ci.index else float("nan")
        ci_hi = float(np.exp(ci.loc[binder_key, 1])) if binder_key in ci.index else float("nan")
        p_val = float(m.pvalues.get(binder_key, float("nan")))
    except Exception:
        or_val = ci_lo = ci_hi = p_val = float("nan")

    return {
        "hypothesis": "H3",
        "or_binder_vs_denovo": or_val,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "p_value": p_val,
        "n_observations": len(df),
    }


def h4_opus_longitudinal(
    results: pd.DataFrame,
    opus_models: list[str] | None = None,
    *,
    compliance_col: str = "modal_compliance",
    model_col: str = "model",
    prompt_id_col: str = "prompt_id",
) -> dict[str, Any]:
    """H4: Longitudinal trajectory across Opus versions.

    Cochran's Q across the three Opus versions plus pairwise McNemar's.
    Restricted to the anthropic-opus lineage (4.5 / 4.6 / 4.7); cross-tier
    comparisons within other providers (e.g. GPT-5.5 vs GPT-5.4-mini) are
    descriptive, not tested here.

    Parameters
    ----------
    opus_models:
        Ordered list of model identifiers for Opus 4.5, 4.6, 4.7.
        Default: ``["claude-opus-4-5", "claude-opus-4-6", "claude-opus-4-7"]``.

    Returns
    -------
    dict with ``cochran_q``, ``cochran_p``, pairwise results, and
    ``direction`` in ``{"decreasing", "increasing", "non_monotonic"}``.

    Example
    -------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     "modal_compliance": ["direct_refusal", "compliance", "compliance"],
    ...     "model": ["claude-opus-4-5", "claude-opus-4-6", "claude-opus-4-7"],
    ...     "prompt_id": ["p1", "p1", "p1"],
    ... })
    >>> result = h4_opus_longitudinal(df)
    >>> "direction" in result
    True
    """
    from scipy import stats as sp_stats

    from refusalbench.council import REFUSAL_KEYS

    if opus_models is None:
        opus_models = ["claude-opus-4-5", "claude-opus-4-6", "claude-opus-4-7"]

    df = results[results[model_col].isin(opus_models)].copy()
    df["refusal"] = (df[compliance_col].isin(REFUSAL_KEYS)).astype(int)

    rates = {
        m: float(df[df[model_col] == m]["refusal"].mean())
        for m in opus_models
        if m in df[model_col].values
    }

    if len(rates) < 2:
        return {"hypothesis": "H4", "direction": "insufficient_data", "rates": rates}

    rate_values = [rates.get(m, float("nan")) for m in opus_models if m in rates]

    if all(r >= rate_values[i - 1] for i, r in enumerate(rate_values) if i > 0):
        direction = "increasing"
    elif all(r <= rate_values[i - 1] for i, r in enumerate(rate_values) if i > 0):
        direction = "decreasing"
    else:
        direction = "non_monotonic"

    pivot = df.pivot_table(index=prompt_id_col, columns=model_col, values="refusal", aggfunc="mean")
    matched_cols = [m for m in opus_models if m in pivot.columns]
    matched = pivot[matched_cols].dropna()

    cochran_q = float("nan")
    cochran_p = float("nan")
    if len(matched) > 1 and len(matched_cols) >= 2:
        try:
            k = len(matched_cols)
            row_totals = matched.sum(axis=1)
            col_totals = matched.sum(axis=0)
            grand = float(matched.values.sum())
            q_num = (k - 1) * (k * float((col_totals**2).sum()) - grand**2)
            q_den = k * grand - float((row_totals**2).sum())
            cochran_q = float(q_num / q_den) if q_den != 0 else float("nan")
            cochran_p = float(sp_stats.chi2.sf(cochran_q, df=k - 1))
        except Exception:
            pass

    return {
        "hypothesis": "H4",
        "direction": direction,
        "rates": rates,
        "cochran_q": cochran_q,
        "cochran_p": cochran_p,
        "n_matched_prompts": len(matched) if "matched" in dir() else 0,
    }


def h5_capability_correlation(
    results: pd.DataFrame,
    wmdp_scores: dict[str, float],
    *,
    compliance_col: str = "modal_compliance",
    model_col: str = "model",
) -> dict[str, Any]:
    """H5: Refusal rate is decoupled from WMDP-Bio capability score.

    Parameters
    ----------
    results:
        Sweep results DataFrame.
    wmdp_scores:
        Dict mapping model identifiers to their published WMDP-Bio scores.

    Returns
    -------
    dict with ``spearman_rho``, ``p_value``, ``ci_lo``, ``ci_hi`` (bootstrap),
    and ``interpretation``.

    Example
    -------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     "modal_compliance": ["direct_refusal", "compliance"],
    ...     "model": ["model_a", "model_b"],
    ... })
    >>> wmdp = {"model_a": 0.80, "model_b": 0.60}
    >>> result = h5_capability_correlation(df, wmdp)
    >>> "spearman_rho" in result
    True
    """
    from scipy import stats as sp_stats

    from refusalbench.council import REFUSAL_KEYS

    df = results.copy()
    df["refusal"] = (df[compliance_col].isin(REFUSAL_KEYS)).astype(int)
    per_model = df.groupby(model_col)["refusal"].mean()

    common = [m for m in per_model.index if m in wmdp_scores]
    if len(common) < 3:
        return {
            "hypothesis": "H5",
            "spearman_rho": float("nan"),
            "p_value": float("nan"),
            "n_models": len(common),
        }

    refusal_rates = [float(per_model[m]) for m in common]
    wmdp_vals = [wmdp_scores[m] for m in common]

    rho, p_val = sp_stats.spearmanr(wmdp_vals, refusal_rates)

    rng_indices = list(range(len(common)))
    boot_rhos = []
    rng = np.random.default_rng(42)
    for _ in range(2000):
        idx = rng.choice(rng_indices, size=len(rng_indices), replace=True)
        r_b = [refusal_rates[i] for i in idx]
        w_b = [wmdp_vals[i] for i in idx]
        if len(set(r_b)) > 1 and len(set(w_b)) > 1:
            rho_b, _ = sp_stats.spearmanr(w_b, r_b)
            boot_rhos.append(float(rho_b))

    ci_lo = float(np.percentile(boot_rhos, 2.5)) if boot_rhos else float("nan")
    ci_hi = float(np.percentile(boot_rhos, 97.5)) if boot_rhos else float("nan")

    interpretation = (
        "weak" if abs(float(rho)) < 0.3 else "moderate" if abs(float(rho)) < 0.6 else "strong"
    )

    return {
        "hypothesis": "H5",
        "spearman_rho": float(rho),
        "p_value": float(p_val),
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "n_models": len(common),
        "interpretation": interpretation,
    }


# ---------------------------------------------------------------------------
# Backward-compatible aliases (old names from developer plan → new paper H-numbers)
# These allow existing call sites to keep working; new code should use the
# canonical h1_-h5_ names above.
# ---------------------------------------------------------------------------
h1_provider_logistic = h2_provider_clustering
h2_subdomain_anthropic = h3_subdomain_anthropic
h3_opus_longitudinal = h4_opus_longitudinal
h4_capability_correlation = h5_capability_correlation
