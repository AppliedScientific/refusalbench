# Prompt set v1.0

Each JSON file in `benign/`, `borderline/`, or `dual_use/` defines one
prompt. Prompts are organised in **paired sets of three** — one per
tier, all on the same subdomain — so refusal behavior can be compared
on matched-difficulty triples.

## Schema

```jsonc
{
  "prompt_id":       "binder_001_benign",      // unique within version
  "subdomain":       "binder_design",          // Subdomain enum value
  "tier":            "benign",                 // matches parent dir
  "paired_with":     [                         // 0 or 2 prompt_ids
    "binder_001_borderline",
    "binder_001_dual_use"
  ],
  "prompt":          "<prompt text shown to the model>",
  "source_citation": "<paper, dataset, or synthesis method>",
  "language":        "en",                     // ISO 639-1
  "notes":           null                      // or a free-form string
}
```

The `notes` string `"synthetic placeholder"` marks scaffold-stage
stand-ins that must be replaced before a real sweep.

## Validation

Run `python scripts/validate_prompts.py` to check:

- All required fields present
- Subdomain and tier in the registered enums
- Tier in JSON matches parent directory
- `paired_with` references resolve and reciprocate
- No duplicate prompt_ids
- Every paired set spans exactly the three tiers

CI runs this on every push.

## Freezing

Once the prompt set is finalized for a sweep, add an empty `.frozen`
marker file at this directory level:

```bash
bash scripts/freeze_prompt_set.sh
```

Subsequent edits should be done by bumping to a new version directory
(`v1.1/`) rather than mutating `v1.0/`.
