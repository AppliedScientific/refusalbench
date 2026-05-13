# Deliverable 1 — Multilevel Regression Results

**Outcome:** `is_refused = modal_compliance in {direct_refusal, indirect_refusal, non_responsive}`  
**Dataset:** `results/snapshots/2026-05/council/adjudicated.csv`, Llama 3.3 70B excluded  
**N = 11,979** observations · 17 models · 141 prompts  
**Fixed effects:** `is_anthropic + C(subdomain) + C(tier)`

---

## Specification comparison

| Spec | Description | OR | 95% CI | Note |
|---|---|---:|---|---|
| **S1** (current paper) | Logistic + cluster-robust SE, clustered on `prompt_id` | **19.90** | [13.75, 28.80] | — |
| **S2** | GEE, marginal logistic, clustered on `model_id` | **19.90** | [5.18, 76.47] | 17 clusters; honest but wide |
| **S3** | BinomialBayesMixedGLM (VB), `(1\|model_id) + (1\|prompt_id)` | **16.49** | [14.72, 18.48] | VB CI is **too narrow** (mean-field underestimates posterior variance) |

**Point estimate summary:** All three specifications give OR ≥ 16.5. The lower bound across all specifications is 5.18 (GEE, S2). The qualitative conclusion is unchanged: Anthropic models have substantially higher refusal odds on this domain than non-Anthropic frontier models.

---

## Variance components (S3 — BinomialBayesMixedGLM VB)

| Random effect | σ² (exp of log-variance posterior mean) |
|---|---:|
| `model_id` | **2.839** |
| `prompt_id` | **0.869** |

The `model_id` variance component (σ² = 2.839) is substantial, confirming meaningful between-model heterogeneity not captured by the `is_anthropic` fixed effect alone. This validates the reviewer's concern: prompt-level clustering alone is insufficient when the key predictor varies at the model level.

---

## Log-likelihood and AIC (S1 — cluster-robust logistic)

| Statistic | Value |
|---|---:|
| Log-likelihood | −5,674.8 |
| AIC | 11,371.7 |

Note: S3 (VB) uses ELBO (evidence lower bound) as the fit criterion, not log-likelihood; direct AIC comparison between S1 and S3 is not meaningful.

---

## Convergence warnings

- **S1:** None
- **S2:** None
- **S3:** None (VB converged without warning; however, VB's mean-field approximation is known to underestimate posterior variance regardless of convergence status)

---

## Note on paper's cited OR = 23.51 [16.26, 34.00]

The current `adjudicated.csv` snapshot gives OR = 19.90 under the same formula and prompt_id clustering. The paper's cited value was likely computed on an earlier snapshot with a different model composition or trial count. The current OR is lower because the dataset now includes additional non-Anthropic models with non-trivial refusal rates (e.g., Kimi K2.6 at 95.0%, GPT-5.5 at 66.4%) that dilute the Anthropic contrast. **The §3.2.2 sentence should update the cited OR to 19.90 from the current snapshot, with the GEE model_id CI [5.18, 76.47] reported alongside to satisfy the reviewer's concern.**

---

## Recommended §3.2.2 update

> "To address the concern that prompt_id-only clustering underestimates variance when the key predictor (`is_anthropic`) varies at the model level, we re-estimated the model using marginal logistic regression (GEE) with model-level clustering (17 clusters). The point estimate is unchanged (OR = 19.90), and the wider CI [5.18, 76.47] reflects the limited number of model-level clusters rather than a weaker effect. A variational Bayes logistic mixed-effects model (random intercepts for both `model_id` and `prompt_id`) gives OR = 16.49 and confirms substantial model-level heterogeneity (σ²_model = 2.84), consistent with the cluster-robust result. Under all specifications the lower bound of the Anthropic effect exceeds 5×."

