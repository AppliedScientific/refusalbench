# Snapshots

Each subdirectory is one quarterly benchmark run, named `YYYY-MM` for the month it was collected. Snapshots are immutable after completion — add a new directory for the next run rather than modifying an existing one.

## Directory layout

```
snapshots/
  2026-05/
    manifest.json          # run metadata (see below)
    sweep_models.json      # frozen copy of config/sweep_models.json used for this run
    council.json           # frozen copy of council/v1.0.json used for this run
    eval/                  # one CSV per model: prompt_id, model, trial_idx, response_text, ...
    council/
      adjudicated.csv      # one row per (prompt_id, model, trial_idx): modal_compliance, subdomain, tier
    figures/               # PDF + PNG exports for this snapshot
    summary.md             # human-written headline stats and notable changes vs prior snapshot
```

## manifest.json fields

| Field | Meaning |
|---|---|
| `snapshot_label` | The `YYYY-MM` string identifying this run |
| `started_at` / `completed_at` | ISO-8601 UTC timestamps; `completed_at` is `null` while sweep is running |
| `prompt_version` | Which prompt freeze was used (e.g. `v1.0`) |
| `council_version` | Which judge config was used (e.g. `v1.0`) |
| `git_sha` | Full SHA of the repo commit at run time — pin-points exact code and config |
| `seed` | Global random seed (default 42) — used for trial reproducibility |
| `n_prompts` | Number of unique prompts evaluated |
| `n_trials` | Trials per (prompt, model) cell |
| `total_invocations` | `n_prompts × n_trials × n_models` |
| `data_provenance` | SHA-256 of every annotation file in `data/`; UniProt release; Open Targets version |
| `models` | List of model entries with `model_id`, `display_name`, `provider`, `organization`, `jurisdiction` |

## Reproducing or comparing runs

To reproduce a run exactly, check out the `git_sha` recorded in `manifest.json`, restore the same `.env` credentials, and re-run with the same `--snapshot` label (the runner skips already-completed cells, so it is safe to re-run):

```bash
git checkout <git_sha>
python scripts/run_sweep_all.py --snapshot 2026-05
```

To compare two snapshots longitudinally:

```python
from pathlib import Path
from refusalbench.analysis.longitudinal import compare_snapshots

df = compare_snapshots(Path("snapshots/2026-05"), Path("snapshots/2026-08"))
print(df[["lineage", "rate_a", "rate_b", "delta"]].sort_values("delta", ascending=False))
```

The comparison groups on `lineage` (from `config/model_lineage.json`), not raw `model_id`, so results remain meaningful even when a provider ships a new model version between snapshots.
