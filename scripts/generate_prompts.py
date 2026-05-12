#!/usr/bin/env python3
# ARCHIVED — The v1.0 prompt set (141 prompts) is frozen at git tag
# `prompts-v1.0-frozen` and committed to prompts/v1.0/. This script
# was used during initial prompt generation and is retained for
# historical reference only. Do not use it to modify the frozen set.
# To re-run the benchmark, use scripts/run_sweep_all.py instead.

"""Master orchestration script for deterministic prompt set generation.

This script runs the full Layer A (deterministic) pipeline, and optionally
the Layer B (QC council) audit. The benchmark JSON output is identical
regardless of whether --run-qc-council is present.

Usage:
    python scripts/generate_prompts.py \\
        --seed 42 \\
        --opentargets-version 24.06 \\
        --catalogue-version v1.0

    # With optional QC audit:
    python scripts/generate_prompts.py \\
        --seed 42 \\
        --opentargets-version 24.06 \\
        --catalogue-version v1.0 \\
        --run-qc-council
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


@click.command()
@click.option("--seed", default=42, show_default=True, help="RNG seed for all sampling operations.")
@click.option(
    "--opentargets-version",
    default="24.06",
    show_default=True,
    help="Open Targets data release version.",
)
@click.option(
    "--catalogue-version", default="v1.0", show_default=True, help="Catalogue version tag."
)
@click.option("--sampling-config", default="benchmark/config/sampling_config.json", show_default=True)
@click.option("--template-config", default="benchmark/config/template_config.json", show_default=True)
@click.option(
    "--output-dir",
    default="benchmark/prompts/v1.0",
    show_default=True,
    help="Output directory for prompt JSONs.",
)
@click.option(
    "--catalogues-dir",
    default="data/catalogues",
    show_default=True,
    help="Pre-built catalogues directory.",
)
@click.option(
    "--run-qc-council",
    is_flag=True,
    default=False,
    help="Run optional LLM QC council after generation.",
)
@click.option("--qc-config", default="benchmark/config/qc_council_config.json", show_default=True)
@click.option("--qc-output-dir", default="results/qc/v1.0", show_default=True)
@click.option(
    "--dry-run", is_flag=True, default=False, help="Validate pipeline without writing output."
)
def main(
    seed: int,
    opentargets_version: str,
    catalogue_version: str,
    sampling_config: str,
    template_config: str,
    output_dir: str,
    catalogues_dir: str,
    run_qc_council: bool,
    qc_config: str,
    qc_output_dir: str,
    dry_run: bool,
) -> None:
    """Generate the RefusalBench v1.0 prompt set deterministically."""
    root = _REPO_ROOT
    sampling_cfg_path = root / sampling_config
    template_cfg_path = root / template_config
    output_path = root / output_dir
    catalogues_path = root / catalogues_dir

    logger.info("RefusalBench prompt generator starting")
    logger.info(
        "  seed=%d  ot_version=%s  catalogue=%s", seed, opentargets_version, catalogue_version
    )

    # Load configs
    with sampling_cfg_path.open() as f:
        sampling_cfg = json.load(f)

    # Sanity-check expected counts
    experimental = sampling_cfg.get("experimental_subdomains", {})
    expected_paired_sets = sum(v.get("paired_sets", 0) for v in experimental.values())
    control_total = sum(
        v.get("benign_only", 0) for v in sampling_cfg.get("control_subdomains", {}).values()
    )
    expected_total = expected_paired_sets * 3 + control_total
    logger.info(
        "  Target: %d experimental paired sets x 3 + %d controls = %d prompts",
        expected_paired_sets,
        control_total,
        expected_total,
    )

    # Layer A: Deterministic core
    logger.info("Layer A: Running deterministic pipeline")
    prompts = _run_layer_a(
        catalogues_path=catalogues_path,
        sampling_cfg=sampling_cfg,
        template_cfg_path=template_cfg_path,
        seed=seed,
        catalogue_version=catalogue_version,
    )

    logger.info("Generated %d prompts", len(prompts))

    # Hard validation
    from refusalbench.prompt_build.validators import HardValidator

    validator = HardValidator()
    paired_sets_ids = _extract_paired_sets(prompts)
    result = validator.validate_set(
        [p for p in prompts],
        paired_sets_ids,
    )
    if not result.passed:
        logger.error("Hard validation FAILED with %d errors:", len(result.errors))
        for pid, rule, msg in result.errors[:20]:
            logger.error("  [%s] %s: %s", pid, rule, msg)
        if not dry_run:
            sys.exit(1)
    else:
        logger.info("Hard validation passed")

    if result.warnings:
        logger.warning(
            "%d validation warnings (synthetic placeholders, etc.):", len(result.warnings)
        )
        for pid, rule, msg in result.warnings:
            logger.warning("  [%s] %s: %s", pid, rule, msg)

    # Write output
    if not dry_run:
        _write_prompts(prompts, output_path)
        logger.info("Wrote %d prompts to %s", len(prompts), output_path)
    else:
        logger.info("Dry run — not writing output")

    # Layer B: Optional QC council
    if run_qc_council:
        logger.info("Layer B: Running optional QC council (this does NOT change the benchmark)")
        _run_layer_b(
            prompts=prompts,
            qc_config_path=root / qc_config,
            output_dir=root / qc_output_dir,
            dry_run=dry_run,
        )
    else:
        logger.info("Skipping optional QC council (pass --run-qc-council to enable)")

    logger.info("Done.")


def _run_layer_a(
    catalogues_path: Path,
    sampling_cfg: dict[str, object],
    template_cfg_path: Path,
    seed: int,
    catalogue_version: str,
) -> list[dict[str, object]]:
    """Run the deterministic core pipeline and return prompt dicts."""
    from refusalbench.prompt_build.pipeline import render_all
    from refusalbench.prompt_build.sampling import sample_controls, sample_paired_sets
    from refusalbench.prompt_build.tier_rules import load_and_assign_tiers

    # Load catalogues
    catalogue_records = _load_catalogues(catalogues_path, sampling_cfg)
    logger.info("Loaded %d candidate records from catalogues", len(catalogue_records))

    # Tier assignment
    assigned = load_and_assign_tiers(catalogue_records)
    logger.info("Tier assignment: %d records assigned", sum(len(v) for v in assigned.values()))

    # Sampling
    paired_records = sample_paired_sets(assigned, sampling_cfg, seed=seed)
    control_records = sample_controls(assigned, sampling_cfg, seed=seed)
    logger.info("Sampled %d paired sets + %d controls", len(paired_records), len(control_records))

    # Rendering
    prompts = render_all(
        paired_records=paired_records,
        control_records=control_records,
        template_cfg_path=template_cfg_path,
        seed=seed,
        source_version=catalogue_version,
    )
    return prompts


def _load_catalogues(
    catalogues_path: Path,
    sampling_cfg: dict[str, object],
) -> list[object]:
    """Load all catalogue JSONL files from the catalogues directory."""
    records: list[object] = []
    if not catalogues_path.exists():
        logger.warning("Catalogues directory %s does not exist; returning empty", catalogues_path)
        return records

    for jsonl_file in sorted(catalogues_path.glob("*.jsonl")):
        with jsonl_file.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        records.append(data)
                    except json.JSONDecodeError as exc:
                        logger.warning("Skipping malformed line in %s: %s", jsonl_file, exc)
    return records


def _extract_paired_sets(prompts: list[dict[str, object]]) -> list[list[str]]:
    """Extract paired set groupings from prompt paired_with fields."""
    pid_to_paired: dict[str, list[str]] = {
        str(p["prompt_id"]): list(p.get("paired_with", [])) for p in prompts
    }

    seen: set[str] = set()
    result: list[list[str]] = []
    for pid, partners in pid_to_paired.items():
        if pid in seen or not partners:
            continue
        group = {pid} | set(partners)
        result.append(sorted(group))
        seen.update(group)
    return result


def _write_prompts(prompts: list[dict[str, object]], output_dir: Path) -> None:
    """Write each prompt as an individual JSON file under the correct tier subdirectory."""
    for p in prompts:
        tier = str(p.get("tier", "benign"))
        tier_dir = output_dir / tier
        tier_dir.mkdir(parents=True, exist_ok=True)
        pid = str(p["prompt_id"])
        with (tier_dir / f"{pid}.json").open("w") as f:
            json.dump(p, f, indent=2)


def _run_layer_b(
    prompts: list[dict[str, object]],
    qc_config_path: Path,
    output_dir: Path,
    dry_run: bool,
) -> None:
    """Run the optional QC council audit (Layer B)."""
    with qc_config_path.open() as f:
        qc_cfg = json.load(f)

    logger.info("QC council: %d judges configured", len(qc_cfg.get("panel", [])))

    if dry_run:
        logger.info("Dry run — skipping actual QC API calls")
        return

    # Actual QC council invocation happens here in a real run.
    # Requires OPENROUTER_API_KEY.
    logger.warning("QC council API calls not implemented yet. Run scripts/run_prompt_qc_council.py")


if __name__ == "__main__":
    main()
