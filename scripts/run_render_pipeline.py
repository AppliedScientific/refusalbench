#!/usr/bin/env python3
"""Run the full prompt rendering pipeline.

Reads all catalogue JSONL files, assigns tiers, samples paired sets per bundle,
renders prompts via templates, and writes one JSON file per prompt to
benchmark/prompts/v1.0/{tier}/.

Usage:
    python scripts/run_render_pipeline.py \\
        --catalogue-dir data/catalogues \\
        --output-dir benchmark/prompts/v1.0 \\
        --template-config benchmark/config/template_config.json \\
        --sampling-config benchmark/config/sampling_config.json \\
        --seed 42
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from refusalbench.prompt_build.pipeline import render_all  # noqa: E402
from refusalbench.prompt_build.sampling import sample_paired_sets  # noqa: E402
from refusalbench.prompt_build.tier_rules import load_and_assign_tiers  # noqa: E402

logger = logging.getLogger(__name__)


@click.command()
@click.option("--catalogue-dir", default="data/catalogues", show_default=True)
@click.option("--output-dir", default="benchmark/prompts/v1.0", show_default=True)
@click.option("--template-config", default="benchmark/config/template_config.json", show_default=True)
@click.option("--sampling-config", default="benchmark/config/sampling_config.json", show_default=True)
@click.option("--seed", default=42, show_default=True, type=int)
@click.option("--dry-run", is_flag=True, default=False, help="Print prompts without writing files.")
def main(
    catalogue_dir: str,
    output_dir: str,
    template_config: str,
    sampling_config: str,
    seed: int,
    dry_run: bool,
) -> None:
    """Render all prompts from catalogue JSONL files."""
    cat_dir = _REPO_ROOT / catalogue_dir
    out_dir = _REPO_ROOT / output_dir
    tmpl_path = _REPO_ROOT / template_config
    samp_path = _REPO_ROOT / sampling_config

    with samp_path.open() as f:
        sampling_cfg: dict[str, object] = json.load(f)

    # Load all catalogue records from JSONL files
    all_raw: list[object] = []
    for jsonl_path in sorted(cat_dir.glob("*.jsonl")):
        with jsonl_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    all_raw.append(json.loads(line))
    logger.info("Loaded %d raw catalogue records", len(all_raw))

    # Assign tiers
    assigned = load_and_assign_tiers(all_raw)
    for tier_key, records in assigned.items():
        logger.info("  Tier %s: %d records", tier_key, len(records))

    # Sample paired sets
    pairs = sample_paired_sets(assigned, sampling_cfg, seed=seed)
    logger.info("Sampled %d paired sets", len(pairs))

    if not pairs:
        logger.warning(
            "No paired sets sampled. "
            "Ensure bundle_definitions.csv is populated and catalogues are built."
        )

    # Render all prompts (no control records for v1.0 experimental pass)
    prompts = render_all(
        paired_records=pairs,
        control_records=[],
        template_cfg_path=tmpl_path,
        seed=seed,
        source_version="v1.0",
    )
    logger.info("Rendered %d prompts", len(prompts))

    if dry_run:
        for p in prompts:
            print(f"\n--- {p['prompt_id']} ({p['tier']}) ---")
            print(p["prompt"])
        return

    # Write prompt JSON files
    for p in prompts:
        tier = str(p["tier"])
        tier_dir = out_dir / tier
        tier_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{p['prompt_id']}.json"
        out_path = tier_dir / fname
        with out_path.open("w") as f:
            json.dump(p, f, indent=2)
        logger.info("  Wrote %s/%s", tier, fname)

    logger.info("Done. Wrote %d prompt files to %s", len(prompts), out_dir)

    # Summary by tier
    tier_counts: dict[str, int] = {}
    for p in prompts:
        tier_counts[str(p["tier"])] = tier_counts.get(str(p["tier"]), 0) + 1
    for tier, count in sorted(tier_counts.items()):
        logger.info("  %s: %d", tier, count)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
