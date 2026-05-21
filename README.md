# RefusalBench

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/AppliedScientific/refusalbench/actions/workflows/ci.yml/badge.svg)](https://github.com/AppliedScientific/refusalbench/actions/workflows/ci.yml)
[![HF Space](https://img.shields.io/badge/%F0%9F%A4%97%20Space-RefusalBench-blue)](https://huggingface.co/spaces/AppliedScientific/refusalbench)
[![Dataset](https://img.shields.io/badge/%F0%9F%A4%97%20Dataset-refusalbench-blue)](https://huggingface.co/datasets/AppliedScientific/refusalbench)
[![Paper](https://img.shields.io/badge/paper-coming%20soon-b31b1b.svg)](#citation)

**RefusalBench** is a modular, reproducible, evergreen benchmark for tracking frontier LLM refusal on biological research prompts across successive model generations. It evaluates 19 frontier models on 141 matched-triple prompts spanning eight protein-design subdomains and three biological risk tiers (benign / borderline / dual-use), using a three-judge AI council to classify each response on a five-class compliance ladder.

The v1.0 prompt set and the inaugural May 2026 snapshot (13,389 adjudicated rows across 19 models, v1.1-frozen) are fully committed to this repository. All statistical analyses can be re-run without API keys from the committed data.

---

## Quickstart

```bash
git clone https://github.com/AppliedScientific/refusalbench
cd refusalbench

# Create and activate a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

make install        # pip install -e ".[dev,stats]"
make test           # 324 tests, all mock-driven — no API keys needed
```

A 5-minute end-to-end demo using mock providers and mock judges:

```bash
python3 scripts/run_pilot_categorization.py --demo
```

---

## Repository layout

```
refusalbench/
├── benchmark/
│   ├── prompts/v1.0/           141 frozen prompt JSONs (benign/borderline/dual_use)
│   ├── council/v1.1.json       Three-judge council config (NVIDIA, Cohere, AI21)
│   ├── rubric/v1.0.json        Five-class compliance ladder × 16-category reason taxonomy
│   ├── config/
│   │   ├── sweep_models.json       19-model routing, pricing, jurisdiction metadata
│   │   ├── model_lineage.json      Lineage tracking for longitudinal comparisons
│   │   ├── sampling_config.json    Bundle counts and stratification rules per subdomain
│   │   └── should_refuse_criteria.yaml  Eligibility criteria (C1–C5) for positive-control module
│   └── templates/              Jinja/text templates for prompt rendering
├── data/
│   ├── raw/                    Source annotation tables (UniProt, BSL maps, OT JSONs)
│   ├── catalogues/             Per-subdomain JSONL catalogues (derived, committed)
│   └── bundle_definitions.csv  47-row bundle mapping table
├── results/
│   ├── snapshots/2026-05/      Inaugural sweep: 19 eval CSVs + adjudicated.csv (13,389 rows, v1.1-frozen)
│   ├── pilot/                  Pilot council outputs (pilot categorization CSVs)
│   ├── pretest/                Pre-test sweep CSVs (sonnet-4-6, opus-4-7)
│   ├── should_refuse/          Should-refuse positive-control public manifests
│   └── figures/                Generated paper figures — gitignored, rebuild with `python -m refusalbench.analysis.figures`
├── src/refusalbench/
│   ├── prompts.py              Prompt loader and validator
│   ├── runner.py               Sweep runner with resumption and deduplication
│   ├── council.py              Three-judge aggregation (modal label, Krippendorff α)
│   ├── score.py                Refusal rates, Wilson CIs, bootstrap
│   ├── providers/              anthropic / openrouter / bedrock / mock
│   ├── judges/                 llm_judge / mock
│   └── analysis/
│       ├── stats.py            H1–H5 statistical tests
│       └── figures.py          Figure generation utilities
├── hf_space/                   HuggingFace Space scaffold (Gradio leaderboard, ready to deploy)
├── scripts/                    CLI entry points (see below)
├── tests/                      324 unit tests, all mock-driven
└── docs/
    ├── methodology.md          Full evaluation methodology
    ├── data_schemas.md         Schema reference for every CSV and JSON in the repo
    ├── catalogue_provenance.md Per-protein audit trail (UniProt verification, BSL sources)
    ├── prompt_construction.md  Bundle derivation rules and source literature
    └── adapter_decisions.md    Provider and judge design decision log
```

---

## Key scripts

| Script | Purpose |
|---|---|
| `scripts/run_sweep_all.py` | Full 19-model sweep — creates a dated snapshot |
| `scripts/run_council.py` | Adjudicate an existing sweep snapshot |
| `scripts/should_refuse_cli.py` | Run the should-refuse positive-control module |
| `scripts/validate_prompts.py` | Validate the frozen prompt set integrity |
| `scripts/build_catalogues.py` | Rebuild per-subdomain JSONL catalogues from raw data |

All scripts support `--help`.

---

## Environment setup

Create `.env` from the template:

```bash
cp .env.example .env
```

Required keys for running a new sweep (not needed for analysis-only work):

| Variable | Purpose | How to obtain |
|---|---|---|
| `OPENROUTER_API_KEY` | Routes most models (OpenAI, xAI, Meta, Mistral, Asian providers) | [openrouter.ai/keys](https://openrouter.ai/keys) |
| `BEDROCK_API_KEY` | AWS Bedrock access (Amazon, Mistral, DeepSeek, Qwen, GLM, NVIDIA) | Bedrock console — must be `ABSK`-prefixed format |
| `AWS_REGION` | Bedrock region (default: `us-east-1`) | Standard AWS region string |

**Analysis-only:** No API keys required. All results can be reproduced from the committed `results/snapshots/2026-05/council/adjudicated.csv`.

---

## Running the analysis

Re-run the statistical analyses against the committed snapshot:

```bash
python3 -c "
import pandas as pd, json
from refusalbench.analysis import stats

df   = pd.read_csv('results/snapshots/2026-05/council/adjudicated.csv')
meta = json.load(open('benchmark/config/sweep_models.json'))
print(stats.h2_provider_clustering(df, meta))    # jurisdiction clustering
print(stats.h3_subdomain_anthropic(df, meta))    # subdomain sensitivity
print(stats.h5_capability_correlation(df, meta)) # capability vs refusal
"
```

To run a new snapshot against the same prompt set with updated or additional models:

```bash
python3 scripts/run_sweep_all.py --label 2026-08 --models benchmark/config/sweep_models.json
python3 scripts/run_council.py   --snapshot results/snapshots/2026-08/
```

See [`docs/methodology.md`](docs/methodology.md) for the complete evaluation methodology and [`DEVELOPER.md`](DEVELOPER.md) for the full architecture and contributor guide.

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/methodology.md`](docs/methodology.md) | Full methodology: models, prompts, sweep, council, statistical model, reproducibility |
| [`docs/data_schemas.md`](docs/data_schemas.md) | Schema for every CSV, JSON, and JSONL file |
| [`docs/catalogue_provenance.md`](docs/catalogue_provenance.md) | Per-protein audit trail — UniProt accession verification, BSL source documentation |
| [`docs/prompt_construction.md`](docs/prompt_construction.md) | Bundle derivation rules, subdomain design rationale, source literature |
| [`docs/adapter_decisions.md`](docs/adapter_decisions.md) | Provider/judge design decisions, routing history |
| [`DEVELOPER.md`](DEVELOPER.md) | Architecture deep-dive, adding new models, running new snapshots |

---

## Contributing

Contributions are welcome — new models, updated snapshots, bug fixes, and documentation improvements. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

---

## Citation

If you use RefusalBench in your research, please cite:

```bibtex
@software{refusalbench2026,
  title        = {{RefusalBench}: A Reproducible, Evergreen Benchmark for
                  {LLM} Refusal on Biological Research Prompts},
  author       = {{Applied Scientific}},
  year         = {2026},
  version      = {1.1.0},
  url          = {https://github.com/AppliedScientific/refusalbench},
  note         = {19 frontier models, 141 prompts, 13{,}389 adjudicated trials},
}
```

> **Paper:** _coming soon_ — this README will be updated with the arXiv DOI on publication.
