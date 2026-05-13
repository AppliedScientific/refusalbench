# Deliverable 1 — Multilevel Regression Results

**Outcome:** `is_refused = modal_compliance in {direct_refusal, indirect_refusal, non_responsive}`  
**Dataset:** `results/snapshots/2026-05/council/adjudicated.csv` + `adjudicated_v1.1_nvidia_dedup.csv`, Llama 3.3 70B excluded  
**N = 12,684** observations · 18 models · 141 prompts *(updated v1.1: +705 Nemotron rows)*  
**Fixed effects:** `is_anthropic + C(subdomain) + C(tier)`

---

## Specification comparison

| Spec | Description | OR (pre-v1.1) | OR (v1.1, +Nemotron) | 95% CI (v1.1) | Note |
|---|---|---:|---:|---|---|
| **S1** (current paper) | Logistic + cluster-robust SE, clustered on `prompt_id` | 19.90 | **21.03** | [14.58, 30.34] | p = 1.28×10⁻⁵⁹ |
| **S2** | GEE, marginal logistic, clustered on `model_id` | 19.90 | **21.03** | [5.70, 77.55] | 18 clusters; p = 4.76×10⁻⁶ |
| **S3** | BinomialBayesMixedGLM (VB), `(1\|model_id) + (1\|prompt_id)` | 16.49 | **19.17** | [17.12, 21.46] | VB CI too narrow (mean-field) |

**Point estimate summary (v1.1):** OR ticked up from ~19.90 → 21.03 (S1/S2) because adding Nemotron (2.7% main-benchmark refusal) widens the Anthropic contrast. S3 moved from 16.49 → 19.17 for the same reason. All three specifications give OR ≥ 19. Lower bound (GEE, S2) is 5.70 — unchanged qualitative conclusion.

---

## Variance components (S3 — BinomialBayesMixedGLM VB)

| Random effect | σ² pre-v1.1 | σ² v1.1 (+Nemotron) |
|---|---:|---:|
| `model_id` | 2.839 | **2.698** |
| `prompt_id` | 0.869 | **0.850** |

Both components are stable (Δ ≤ 0.14). The small σ²_model decrease (2.839 → 2.698) is expected: adding Nemotron — a model with clearly low refusal rate well-captured by `is_anthropic=0` — slightly reduces residual model-level heterogeneity. σ²_model = 2.698 remains substantial, confirming meaningful between-model heterogeneity beyond the `is_anthropic` fixed effect. Conclusion unchanged: prompt-level clustering alone is insufficient.

---

## Log-likelihood and AIC (S1 — cluster-robust logistic)

| Statistic | Pre-v1.1 | v1.1 (+Nemotron) |
|---|---:|---:|
| Log-likelihood | −5,674.8 | **−5,902.2** |
| AIC | 11,371.7 | **11,826.4** |
| N | 11,979 | **12,684** |

Note: S3 (VB) uses ELBO (evidence lower bound) as the fit criterion, not log-likelihood; direct AIC comparison between S1 and S3 is not meaningful.

---

## Convergence warnings

- **S1:** None
- **S2:** None
- **S3:** None (VB converged without warning; however, VB's mean-field approximation is known to underestimate posterior variance regardless of convergence status)

---

## Note on paper's cited OR = 23.51 [16.26, 34.00]

The current `adjudicated.csv` snapshot gives OR = 19.90 under the same formula and prompt_id clustering. The paper's cited value was likely computed on an earlier snapshot with a different model composition or trial count. The current OR is lower because the dataset now includes additional non-Anthropic models with non-trivial refusal rates (e.g., Kimi K2.6 at 95.0%, GPT-5.5 at 66.4%) that dilute the Anthropic contrast. **The §3.2.2 sentence should update the cited OR to 21.03 (v1.1 snapshot, N=12,684, 18 non-Anthropic models), with the GEE model_id CI [5.70, 77.55] reported alongside.**

---

## Recommended §3.2.2 update

> "To address the concern that prompt_id-only clustering underestimates variance when the key predictor (`is_anthropic`) varies at the model level, we re-estimated the model using marginal logistic regression (GEE) with model-level clustering (18 clusters, v1.1 dataset). The point estimate is unchanged (OR = 21.03), and the wider CI [5.70, 77.55] reflects the limited number of model-level clusters rather than a weaker effect. A variational Bayes logistic mixed-effects model (random intercepts for both `model_id` and `prompt_id`) gives OR = 19.17 and confirms substantial model-level heterogeneity (σ²_model = 2.70), consistent with the cluster-robust result. Under all specifications the lower bound of the Anthropic effect exceeds 5×."

