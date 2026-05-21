# Contributing to RefusalBench

Thank you for your interest in contributing. Contributions that extend the panel, improve reproducibility, or fix bugs are especially welcome.

---

## Table of contents

1. [Code of conduct](#code-of-conduct)
2. [Ways to contribute](#ways-to-contribute)
3. [Development setup](#development-setup)
4. [Adding a new model](#adding-a-new-model)
5. [Submitting a snapshot](#submitting-a-snapshot)
6. [Pull request checklist](#pull-request-checklist)
7. [Style guide](#style-guide)

---

## Code of conduct

This project follows the [Contributor Covenant v2.1](CODE_OF_CONDUCT.md). By participating you agree to abide by its terms.

---

## Ways to contribute

| Type | What to do |
|---|---|
| 🐛 Bug fix | Open an issue first, then a PR referencing it |
| 📊 New model | Add routing metadata + run a sweep (see below) |
| 📸 New snapshot | Sweep existing models at a later date, open a PR with the dated snapshot |
| 📝 Documentation | Fix, clarify, or extend any file under `docs/` |
| 🔬 Statistical analysis | Add or improve hypothesis tests in `src/refusalbench/analysis/stats.py` |

Please open an issue before investing significant effort in a large change — it avoids duplication and ensures the direction aligns with the project goals.

---

## Development setup

```bash
git clone https://github.com/AppliedScientific/refusalbench
cd refusalbench
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,stats]"
make test          # 324 tests, all mock-driven — no API keys needed
```

Lint and type-check:

```bash
ruff check src/ tests/
mypy src/
```

---

## Adding a new model

1. **Add routing metadata** to `benchmark/config/sweep_models.json` — provider key, model ID, jurisdiction, pricing tier.
2. **Add display metadata** to `_MODEL_META` in `src/refusalbench/analysis/figures.py` and to `MODEL_META` in `hf_space/app.py`.
3. **Run a sweep** (requires provider API keys):
   ```bash
   python3 scripts/run_sweep_all.py --label YYYY-MM --models benchmark/config/sweep_models.json
   python3 scripts/run_council.py   --snapshot results/snapshots/YYYY-MM/
   ```
4. **Open a PR** with the snapshot CSV(s) and updated metadata. Include refusal rates and Wilson CIs in the PR description.

See [DEVELOPER.md](DEVELOPER.md) for a full walkthrough of the sweep pipeline.

---

## Submitting a snapshot

A snapshot PR must include:

- `results/snapshots/YYYY-MM/` directory with one CSV per model
- `results/snapshots/YYYY-MM/council/adjudicated.csv` (13-column schema per `docs/data_schemas.md`)
- Updated model counts in README if the panel changes
- A brief description of any model version changes since the prior snapshot

Snapshots are frozen on merge and never modified retroactively.

---

## Pull request checklist

Before requesting review, confirm:

- [ ] `make test` passes with no failures
- [ ] `ruff check src/ tests/` passes with no errors
- [ ] New code has type annotations and passes `mypy src/`
- [ ] Any new functionality has corresponding tests
- [ ] Documentation is updated where relevant
- [ ] No API keys, credentials, or private prompt text committed

---

## Style guide

- **Python ≥ 3.11**, line length 100, Ruff-enforced
- Type annotations on all public functions
- `from src.logging_config import get_logger` — no `print()` in library code
- Deterministic outputs where possible (fix random seeds, `temperature=0`)
- Commit messages: imperative mood, ≤ 72 characters subject line

---

Questions? Open a [GitHub Discussion](https://github.com/AppliedScientific/refusalbench/discussions) or an issue.
