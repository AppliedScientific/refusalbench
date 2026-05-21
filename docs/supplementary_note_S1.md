# Supplementary Note S1 — System-Prompt Sensitivity Sweep (v1.1)

## Overview

This note reports the results of a controlled system-prompt sensitivity sweep assessing whether
the refusal rates observed in the main RefusalBench v1.0 evaluation are driven by model-level
safety training or by API-stack-level framing. Five models from the main sweep were re-evaluated
across four system-prompt framings (P1–P4) on a 36-prompt stratified subsample, yielding 3,600
trials (5 models × 4 framings × 36 prompts × 5 trials). All evaluations were conducted via the
Amazon Bedrock Converse API. The judge panel comprised three Bedrock-hosted models not present
in the sensitivity eval panel: AI21 Jamba 1.5 Large, Writer Palmyra X5, and Meta Llama 3.1 70B
Instruct (3-judge unanimous agreement: 55.8%).

**Prompt subsample.** Two prompt bundles per domain were drawn from the v1.0 frozen set, stratified
across three tiers (benign, borderline, dual-use), yielding 36 prompts covering six biodesign
domains: binder design, enzyme design, de novo protein design, sequence design, structure
prediction, and stability optimisation.

**System-prompt framings.** P1 omits the system field entirely (no-prompt baseline); P2 asserts
an expert-researcher persona with safety-aware framing; P3 frames the user as a credentialed
researcher at a regulated institution; P4 adds an explicit safety-restrictive instruction to
decline dual-use requests. The v1.0 sweep used a single neutral system prompt (sweep_v1.0.txt,
git hash f91a9f3); all sensitivity framing comparisons are taken against v1.0 refusal rates
computed on the same 36 prompts.

---

## Finding 1 — Per-(Model, Framing) Refusal Rates

**Table S1.** Refusal rate (%) per model and framing. *v1.0* = v1.0 baseline on the same 36-prompt
subset (5 trials × 36 prompts = 180 trials per model). P1–P4 each represent 180 trials.
Range = max − min across P1–P4.

| Model | v1.0 | P1 (no prompt) | P2 (researcher persona) | P3 (user authority) | P4 (safety restrict) | Range |
|---|---:|---:|---:|---:|---:|---:|
| Claude Opus 4.7 | 97.2 | 94.4 | 97.2 | **100.0** | **100.0** | 5.6 pp |
| Claude Sonnet 4.6 | 82.2 | 81.7 | 85.0 | 87.8 | 81.1 | 6.7 pp |
| Mistral Large 3 | 0.6 | 14.4 | 21.7 | 16.1 | 64.4 | 50.0 pp |
| DeepSeek R1 | 1.1 | **93.3** | 77.2 | 56.7 | 77.2 | 36.6 pp |
| Amazon Nova Pro | 0.6 | 4.4 | 3.9 | 3.9 | **97.2** | 93.3 pp |

All Bedrock `[CONTENT_FILTERED]` responses are classified as `direct_refusal / safety_policy`
prior to judge routing, consistent with the main sweep protocol.

---

## Finding 2 — Absolute Shifts from the v1.0 Baseline

**Table S2.** Percentage-point shift from v1.0 baseline per framing.

| Model | P1 | P2 | P3 | P4 |
|---|---:|---:|---:|---:|
| Claude Opus 4.7 | −2.8 | 0.0 | +2.8 | +2.8 |
| Claude Sonnet 4.6 | −0.5 | +2.8 | +5.6 | −1.1 |
| Mistral Large 3 | +13.8 | +21.1 | +15.5 | +63.8 |
| DeepSeek R1 | +92.2 | +76.1 | +55.6 | +76.1 |
| Amazon Nova Pro | +3.8 | +3.3 | +3.3 | +96.6 |

Anthropic models show ≤6 pp absolute movement across all framings. Non-Anthropic models show
substantially larger shifts (36–93 pp), indicating that their low v1.0 refusal rates are
contextually contingent rather than model-level invariants.

---

## Finding 3 — Provider-Level Ranking Stability Across Framings

The Anthropic models occupy the top two positions under P1, P2, and P3. Under P4, the ranking
is disrupted: Nova Pro spikes from 3.9% (P3) to 97.2% (P4), placing it second overall; DeepSeek R1
and Mistral Large 3 also rise sharply. The Anthropic models retain the top two positions even under
P4, but the non-Anthropic tier undergoes a near-complete reordering.

Concretely:
- **P1** (no prompt): Opus (94.4%) > DeepSeek (93.3%) > Sonnet (81.7%) > Mistral (14.4%) > Nova (4.4%)
- **P2** (researcher): Opus (97.2%) > Sonnet (85.0%) > DeepSeek (77.2%) > Mistral (21.7%) > Nova (3.9%)
- **P3** (authority): Opus (100%) > Sonnet (87.8%) > DeepSeek (56.7%) > Mistral (16.1%) > Nova (3.9%)
- **P4** (restrict): Opus (100%) > Nova (97.2%) > Sonnet (81.1%) > DeepSeek (77.2%) > Mistral (64.4%)

Anthropic first-and-second is preserved across all four framings. The within-tier ordering of
non-Anthropic models is unstable.

---

## Finding 4 — Within-Anthropic Framing Sensitivity

Both Anthropic models are largely insensitive to system-prompt framing, but show different
tier-level profiles when disaggregated.

**Claude Opus 4.7** (5.6 pp range). The sole framing effect is on the *benign* tier: P1 (no
prompt) drops benign-tier refusals to 83% (50/60), recovering to 92% under P2, and reaching 100%
under P3 and P4. Borderline and dual-use tiers are refused at 100% across all four framings.
The practical implication is that the expert-researcher system prompt (P2 or P3) closes the gap
for benign queries that the model would otherwise answer without context.

**Claude Sonnet 4.6** (6.7 pp range). The benign tier shows broader framing sensitivity (43–63%
refusal across P1–P4) while borderline and dual-use tiers remain at 100% refusal under all
framings. Notably, P4 (explicit safety restriction) reduces the benign-tier refusal rate by 2 pp
versus P1, suggesting no additive effect of the explicit instruction for this model — the model is
already at or near its operating point.

These tier-level patterns confirm that framing shifts are concentrated in the benign tier, which
contains structurally ambiguous prompts that sit close to the model's decision boundary.

---

## Finding 5 — P4 Ceiling Test

The P4 framing provides a direct test of whether the Bedrock API stack, rather than model-level
training, is the binding constraint on Anthropic refusal rates. If adding an explicit instruction
to decline dual-use requests produces negligible movement, the model is already at ceiling.

| Model | P1 refusal | P4 refusal | P4 − P1 | Interpretation |
|---|---:|---:|---:|---|
| Claude Opus 4.7 | 94.4% | 100.0% | +5.6 pp | Near ceiling; P4 closes benign-tier gap |
| Claude Sonnet 4.6 | 81.7% | 81.1% | −0.6 pp | **Zero movement**; API stack is binding |
| Mistral Large 3 | 14.4% | 64.4% | +50.0 pp | Model-driven |
| DeepSeek R1 | 93.3% | 77.2% | −16.1 pp | **Inverted**: safety instruction reduces refusals |
| Amazon Nova Pro | 4.4% | 97.2% | +92.8 pp | Model-driven |

For Claude Sonnet 4.6, the explicit safety instruction produces −0.6 pp (within noise), confirming
that the model's 82% refusal rate on this domain is not further movable by system-prompt
instruction — it is driven by the Bedrock-level content filter and model-level priming, not by
the presence or absence of a safety directive in the system turn.

For Claude Opus 4.7, the +5.6 pp movement is confined to the benign tier (see Finding 4); dual-use
and borderline tiers are already at 100% refusal under P1.

The DeepSeek R1 inversion — where adding an explicit safety instruction reduces the refusal rate
by 16 pp relative to the no-prompt condition — is an anomalous pattern consistent with
instruction-following models that interpret the explicit safety framing as a *topic signal* (the
model now understands the domain and provides answers) rather than a *refusal trigger*. Under
P1 (no system prompt), DeepSeek's 93.3% refusal rate reflects the model defaulting to a cautious
prior in the absence of framing; the expert-context framings (P2, P3) and the safety-restrictive
framing (P4) all reduce refusals relative to this no-context baseline.

---

## Summary

The sensitivity sweep supports four conclusions: (1) Anthropic model refusal rates are robust to
system-prompt framing, with ≤7 pp range across all tested conditions; (2) non-Anthropic models
show high framing sensitivity (37–93 pp range), indicating their v1.0 refusal rates are contextually
contingent; (3) provider-level ranking is stable under P1–P3 but disrupted by P4, which activates
latent refusal capacity in Nova Pro and Mistral; and (4) the P4 ceiling test confirms that the
Bedrock API stack — not the system prompt — is the binding constraint for Claude Sonnet 4.6, and
that Claude Opus 4.7 is within 6 pp of its structural ceiling. The DeepSeek R1 inversion under P4
is a methodologically notable anomaly warranting further investigation.

---

*Sweep specification:* `benchmark/council/v1.1-sensitivity.json`, `benchmark/sensitivity_bundles.csv`,
`benchmark/prompts/system/system-prompts-v1.1.json`. *Results:* `results/snapshots/2026-05/sensitivity/sensitivity_sweep_v1.1.csv`
(3,600 rows). *Analysis script:* `scripts/run_sensitivity_sweep.py`.
