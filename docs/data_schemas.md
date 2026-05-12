# Data Schemas

All tabular data is CSV. No Parquet, no SQLite.

---

## data/bundle_definitions.csv — research-question bundle mapping

Maps sets of three target IDs (one per tier) to a shared bundle ID. One row per bundle.
Used by `scripts/build_catalogues.py` to set `provenance_bundle_id` so the sampling layer
can form valid (benign, borderline, dual_use) triples.

| Column | Type | Description |
|---|---|---|
| `bundle_id` | str | Unique bundle identifier, e.g. `binder_001` |
| `subdomain` | str | Subdomain this bundle belongs to; must be in the subdomain enum |
| `benign_target_id` | str | Source record ID of the benign member (ENSEMBL ID for OT targets) |
| `borderline_target_id` | str | Source record ID of the borderline member (UniProt accession for pathogen proteins) |
| `dual_use_target_id` | str | Source record ID of the dual-use member (UniProt accession) |
| `rationale` | str | Human-readable explanation of why these three targets form a coherent triple |

Rules:
- Each `target_id` (across all three columns) must be unique across all rows. A single
  target cannot belong to two bundles.
- Rows with blank `bundle_id` are silently skipped by `_load_bundle_definitions`.
- Cells may be blank if a target is not yet assigned (partial rows are supported; only
  non-blank target IDs are loaded into the lookup dict).

---

## data/raw/pathogen_targets.json — curated pathogen protein entries

A JSON array where each element represents one pathogen protein for use in the borderline
or dual-use tiers. Pre-curated by a researcher; risk flags are set explicitly and are not
derived from annotation table lookup.

| Field | Type | Required | Description |
|---|---|---|---|
| `uniprot_accession` | str | yes | UniProt Swiss-Prot accession. Used as `source_record_id` in the catalogue. |
| `protein_name` | str | yes | Protein full name as in UniProt recommendedName |
| `gene_name` | str | no | Gene symbol |
| `organism_name` | str | yes | Organism name; must match the format in `bsl_mapping.json` if BSL lookup is needed |
| `organism_bsl` | int\|null | yes | BSL level 1-4, or null if not applicable (e.g. plant toxin where organism is irrelevant) |
| `select_agent` | bool | yes | True if protein is from a CDC/USDA select agent. Maps to `RiskAnnotation.select_agent_flag` |
| `toxin` | bool | yes | True if protein has UniProt KW-0800. Maps to `RiskAnnotation.toxin_flag` |
| `australia_group` | bool | yes | True if protein appears on the Australia Group biological agent control list |
| `who_priority_pathogen` | bool | yes | True if the source organism is on the WHO 2024 priority pathogen list |
| `pandemic_potential` | bool | yes | True if the organism has recognized pandemic potential (e.g. SARS-CoV-2) |
| `target_class` | str | yes | Broad functional classification of the protein |
| `pathogen_family` | str | no | Taxonomic family of the source organism |
| `applicable_subdomains` | list[str] | yes | Which subdomains this protein appears in. The catalogue builder filters by this field. |
| `natural_language_summary` | str | yes | One-sentence description used as the seed for prompt template rendering |

Tier assignment (derived from the fields above by `tier_rules.py`):
- `organism_bsl == 4` OR `select_agent == true` OR `toxin == true` → **dual_use**
- `organism_bsl == 3` (with no dual-use flags) → **borderline**
- `organism_bsl <= 2` with no other flags → **benign** (should not appear in this file)

---

## data/catalogues/*.jsonl — subdomain catalogues

One JSONL file per subdomain. Each line is a JSON object representing one `CandidateRecord`
as serialised by `dataclasses.asdict()`. Written by `scripts/build_catalogues.py`.

### Core identity fields

| Field | Type | Description |
|---|---|---|
| `source_record_id` | str | Primary key within source database. ENSEMBL ID (OT) or UniProt accession (pathogen) |
| `provenance_bundle_id` | str | Bundle ID from `bundle_definitions.csv` lookup, or falls back to `source_record_id` |
| `subdomain` | str | One of the eight registered subdomains |
| `target_name` | str | Human-readable protein/gene name |
| `target_class` | str | Broad class (e.g. "receptor_tyrosine_kinase", "viral surface glycoprotein") |
| `organism_name` | str | Source organism Latin or common name |
| `source_database` | str | `"open_targets"` or `"uniprot"` |
| `source_version` | str | OT release (e.g. `"24.06"`) or UniProt release (e.g. `"2024_05"`) |
| `natural_language_summary` | str | One-sentence description used as template seed |

### Risk annotation (nested dict under `risk`)

| Field | Type | Description |
|---|---|---|
| `organism_bsl` | int\|null | BSL level 1-4 |
| `select_agent_flag` | bool | From CDC/USDA select agent list |
| `australia_group_flag` | bool | From Australia Group control list |
| `australia_group_level` | str\|null | `"core"` triggers dual_use; other values are informational |
| `toxin_flag` | bool | UniProt KW-0800 |
| `who_priority_pathogen_flag` | bool | WHO 2024 priority pathogen list |
| `pandemic_potential_flag` | bool | Recognized pandemic potential |
| `amr_flag` | bool | Antimicrobial resistance relevance |
| `host_entry_factor_flag` | bool | Host entry factor for a pathogen |
| `countermeasure_flag` | bool | Key countermeasure target |
| `explicit_high_restriction` | bool | Manually overridden to high restriction |

### Optional provenance fields

| Field | Type | Description |
|---|---|---|
| `uniprot_id` | str\|null | UniProt accession (populated for pathogen records) |
| `disease_name` | str\|null | Associated disease (populated for some OT records) |
| `efo_id` | str\|null | EFO disease ID (OT records) |
| `pathogen_family` | str\|null | Taxonomic family (pathogen records) |
| `protein_class` | str\|null | Detailed protein class from OT |
| `evidence_score` | float\|null | OT association evidence score |
| `disease_area` | str\|null | Therapeutic area |
| `clinical_stage` | str\|null | Highest clinical stage (OT) |

### Template / rendering fields

| Field | Type | Description |
|---|---|---|
| `template_family` | str | Template family key. Default: `"default"` |
| `prompt_style_profile` | str | Style profile. Default: `"standard"` |
| `lexical_risk_features` | list[str] | Risk-relevant tokens extracted for vocabulary balance check |
| `additional_fields` | dict[str, str] | Pass-through fields from source (control tasks use this) |

---

## data/raw/bsl_mapping.json — organism BSL level table

A JSON object mapping exact organism name strings (case-insensitive) to BSL integer levels
(1-4). A `_comment` key is reserved for documentation and ignored by the loader.

Used by `_annotate_risk` in `build_catalogues.py` to assign `organism_bsl` to OT records
(human proteins). Pathogen records do not use this table — their BSL is pre-curated.

Format: `{"Organism name": <int>, ...}`

---

## data/raw/select_agent_list.json — select agent identifiers

A JSON array of strings. Each non-comment string is a UniProt accession for a protein
from a CDC/USDA select agent. A `_comment` prefix (leading `"_comment:..."`) marks
documentation entries ignored by the loader.

Matched against `target_name` and `organism_name` (normalised, case-insensitive) for OT
records; matched against `source_record_id` for pathogen records (since the accession is
the ID).

**Note:** The current `_annotate_risk` function does exact string matching against
`target_name` and `organism_name`. For OT human proteins this will never match. For
pathogen records the flag is set directly in `pathogen_targets.json`, not derived from
this table. This table is therefore currently informational — it documents which proteins
are select agents, used as a cross-check, but does not affect tier assignment for the
existing catalogues.

---

## data/raw/uniprot_toxin_annotations.json — KW-0800 toxin identifiers

A JSON array of UniProt accessions for proteins with keyword KW-0800 (Toxin) that are
relevant to this benchmark. Verified via UniProt REST API on 7 May 2026.

Same matching rules and same current-informational caveat as `select_agent_list.json`.

---

## data/raw/who_priority_pathogens.json — WHO priority pathogen organisms

A JSON array of organism name strings from the WHO 2024 priority pathogen list.
Matched case-insensitively against `organism_name`. Sets `who_priority_pathogen_flag`
on OT records via `_annotate_risk`. For pathogen records, set directly in JSON.

---

## data/raw/australia_group_list.json — Australia Group control list

A JSON array of UniProt accessions for proteins on the Australia Group dual-use biology
control list. Same structure and matching rules as `select_agent_list.json`.

---

## results/eval/*.csv — sweep output

One row per (prompt_id, model, trial_idx).

| Column | Type | Description |
|---|---|---|
| `prompt_id` | str | Unique prompt identifier |
| `model` | str | Model identifier |
| `trial_idx` | int | Trial index 0-4 |
| `run_seed` | int | seed + trial_idx |
| `response_text` | str | Full model response |
| `latency_ms` | int | API latency in ms |
| `error` | str | Error message (empty if success) |

## results/council/pilot_categorization.csv — per-judge labels

| Column | Type | Description |
|---|---|---|
| `prompt_id` | str | Prompt identifier |
| `judge_id` | str | Council judge identifier |
| `compliance` | str | compliance_level key |
| `reason` | str | reason_category key |
| `parse_failed` | int | 1 if judge output was unparseable |

## results/council/pilot_aggregated.csv — modal labels

| Column | Type | Description |
|---|---|---|
| `prompt_id` | str | Prompt identifier |
| `modal_compliance` | str | Majority compliance label |
| `modal_reason` | str | Majority reason label |
| `compliance_agreement` | float | Fraction of judges agreeing on compliance |
| `reason_agreement` | float | Fraction of judges agreeing on reason |
| `any_parse_failed` | int | 1 if any judge failed to parse |
| `flagged_for_spot_check` | int | 1 if agreement below threshold |
