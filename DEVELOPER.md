# Developer Guide

This document covers the RefusalBench architecture, contributor workflows, and how to extend the benchmark for future snapshots.

---

## Architecture overview

```
                  ┌─────────────────────────────────────────┐
                  │           Prompt set (frozen)            │
                  │  prompts/v1.0/  ·  141 JSON files        │
                  │  47 matched triples × 3 tiers            │
                  └──────────────────┬──────────────────────┘
                                     │
                  ┌──────────────────▼──────────────────────┐
                  │            Sweep runner                  │
                  │  scripts/run_sweep_all.py                │
                  │  src/refusalbench/runner.py              │
                  │  • (prompt, model, trial) deduplication  │
                  │  • atomic writes, resumable              │
                  │  → snapshots/<label>/eval/<model>.csv    │
                  └──────────────────┬──────────────────────┘
                                     │
                  ┌──────────────────▼──────────────────────┐
                  │          Three-judge council             │
                  │  scripts/run_council.py                  │
                  │  src/refusalbench/council.py             │
                  │  • 3 judges vote on each response        │
                  │  • modal label + Krippendorff α          │
                  │  → snapshots/<label>/council/            │
                  │    adjudicated.csv  (12,684 rows)        │
                  └──────────────────┬──────────────────────┘
                                     │
                  ┌──────────────────▼──────────────────────┐
                  │            Statistical analysis          │
                  │  src/refusalbench/analysis/stats.py      │
                  │  src/refusalbench/analysis/figures.py    │
                  │  • O1–O3 tests (Wilson CI, Mann-Whitney, │
                  │    logistic regression, Cochran Q,       │
                  │    McNemar, Spearman ρ, Youden J)        │
                  └─────────────────────────────────────────┘
```

The benchmark is designed so that each stage's outputs are committed. A new contributor can enter at any stage without re-running the prior stages.

---

## Package structure

```
src/refusalbench/
├── __init__.py
├── prompts.py          PromptLoader, PromptValidator (KS test, vocab audit)
├── runner.py           SweepRunner — model invocation, deduplication, logging
├── council.py          CouncilAggregator — 3-judge modal vote, α, spot-check flagging
├── score.py            RefusalScorer — Wilson CIs, bootstrap, tier aggregates
├── providers/
│   ├── base.py         AbstractProvider interface
│   ├── anthropic.py    Direct Anthropic API
│   ├── openrouter.py   OpenRouter (most non-Anthropic models)
│   ├── bedrock.py      AWS Bedrock (Anthropic, Google, Cohere, AI21, Amazon)
│   └── mock.py         Deterministic mock for tests
├── judges/
│   ├── base.py         AbstractJudge interface
│   ├── llm_judge.py    Real judge using OpenRouter / Bedrock
│   └── mock.py         Deterministic mock for tests
└── analysis/
    ├── stats.py        H1–H5 / O1–O3 statistical functions
    └── figures.py      Matplotlib figure generators
```

---

## Running a new snapshot

### 1. Set up credentials

```bash
cp .env.example .env
# Fill in OPENROUTER_API_KEY and AWS_SECRET_ACCESS_KEY
```

### 2. Verify the prompt set

```bash
python scripts/validate_prompts.py
# Expects: 141 prompts, 47 bundles, 3 tiers — all BLAKE2b hashes verified
```

### 3. Run the sweep

```bash
python scripts/run_sweep_all.py --label 2026-08 --models config/sweep_models.json
```

This creates `snapshots/2026-08/eval/<model_id>.csv` for each model. The runner is resumable: if interrupted, re-run the same command and it will skip completed (prompt, model, trial) cells.

### 4. Adjudicate with the council

```bash
python scripts/run_council.py --snapshot snapshots/2026-08/
```

Produces `snapshots/2026-08/council/adjudicated.csv`.

### 5. Run analysis

```bash
python -m refusalbench.analysis.stats \
    --data snapshots/2026-08/council/adjudicated.csv \
    --pc-data metadata/should_refuse_sweep_public.csv \
    --models config/sweep_models.json
```

---

## Adding a new model

1. **Add to `config/sweep_models.json`** — copy an existing entry and fill in:
   - `model_id`: the provider's canonical ID string
   - `display_name`: short human-readable name
   - `provider`: `"anthropic"` | `"openrouter"` | `"bedrock"`
   - `jurisdiction`: `"US"` | `"EU"` | `"Asia"`
   - `organization`: provider company name
   - `role`: `"primary"` | `"longitudinal"` | `"control"`

2. **Verify routing** — run `python scripts/validate_prompts.py` and then a single-model smoke test:
   ```bash
   refusalbench-run --model <model_id> --tier benign --limit 3
   ```

3. **Add to `config/model_lineage.json`** if the model is part of a tracked lineage (e.g., Opus 4.8 extending the Opus series).

No code changes are required for standard API-routed models — the provider classes auto-route based on the `provider` field in `sweep_models.json`.

---

## Adding a new subdomain

1. **Create source records** — add pathogen and benign targets to `data/raw/` following the schema in `docs/data_schemas.md`.
2. **Extend catalogues** — run `python scripts/build_catalogues.py` with the new subdomain flag.
3. **Write prompt templates** — add templates to the relevant template config (see `config/template_config.json`).
4. **Render prompts** — run `python scripts/render_prompts.py --subdomain <new_subdomain>`.
5. **Validate** — run `python scripts/validate_prompts.py`.
6. **Update `config/sampling_config.json`** with the new subdomain's `paired_sets` count and stratification keys.
7. **Do not unfreeze** `prompts-v1.0-frozen` — new subdomains are part of v2.0+.

---

## Council configuration

The council configuration is versioned in `council/`. The inaugural 2026-05 snapshot used **v1.1**:

| Judge | Model | Provider | Routing |
|---|---|---|---|
| `nvidia_nemotron` | NVIDIA Nemotron-70B-Instruct | NVIDIA | OpenRouter |
| `cohere_command_r_plus` | Cohere Command R+ | Cohere | AWS Bedrock |
| `ai21_jamba` | AI21 Jamba 1.5 Large | AI21 | AWS Bedrock |

To change council composition for a new snapshot: create a new versioned file `council/v1.X.json` and pass `--council council/v1.X.json` to `run_council.py`. Never modify an existing versioned council file — downstream comparisons depend on council stability.

---

## Should-refuse positive-control module

The 15 positive-control prompts are evaluated separately from the main benchmark. Their raw text is withheld under responsible-disclosure policy (see `docs/methodology.md §2.6`). To re-run the positive control:

```bash
python scripts/should_refuse_cli.py --models config/sweep_models.json
```

Public artifacts (prompt IDs, per-model classifications, C1–C5 flags) are in `metadata/`. Private artifacts (prompt text, model responses) are stored outside the repository tree.

---

## Tests

```bash
make test                    # full suite with coverage
pytest tests/ -k "stats"     # stats module only
pytest tests/ -v --no-header # verbose
```

All tests use mock providers and mock judges — no API keys needed. The test suite covers prompt loading, runner deduplication, council aggregation, scoring, and figure generation. Adding a test for any new analysis function in `stats.py` before merging is required.

---

## Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
```

Hooks: ruff lint + format, trailing whitespace, YAML/JSON validity, merge-conflict detection, large-file guard (5 MB), and a custom hook that blocks any file matching `*.shouldrefuse.*` patterns from being committed (prevents accidental disclosure of positive-control prompt text).

---

## Quarterly snapshot workflow

A GitHub Actions workflow (`.github/workflows/quarterly_snapshot.yml`) opens a checklist issue on Jan 1, Apr 1, Jul 1, and Oct 1 with the steps to run the next snapshot. The checklist covers: credential rotation, model panel review, sweep execution, council adjudication, analysis re-run, and paper results update.

---

## Known issues / stale artifacts

- `scripts/generate_prompts.py` and `scripts/generate_missing_prompts.py` are archived historical scripts used during initial prompt generation. The v1.0 set is frozen; do not use these to modify it.
- `scripts/tier_rules.py` is a thin CLI shim that delegates to `src/refusalbench/prompt_build/tier_rules.py` — it exists for convenience and does not duplicate logic.
- `.claude/worktrees/` may appear in the working tree if Claude Code was used during development. These directories are not tracked and can be safely deleted.
