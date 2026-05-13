"""Resumption-safe benchmark sweep for the v1.1 Nemotron panel addition.

Evaluates nvidia.nemotron-super-3-120b on all 141 main-benchmark prompts ×
5 trials (705 eval calls), then runs the two-judge Bedrock council
(AI21 Jamba + Meta Llama 3.1 70B) on each response (1,410 judge calls).

Results are written to results/snapshots/2026-05/council/adjudicated_v1.1_nvidia.csv
in the same schema as the main adjudicated.csv, with an extra `snapshot_version`
column for traceability. After review, rows can be appended to adjudicated.csv.

Should-refuse positive control (75 trials) is handled separately via the
existing should_refuse_cli.py --run-sweep --only nvidia_nemotron3 workflow
(requires --private-artifacts-dir pointing to the private prompt store).

Usage
-----
    # Dry-run: print plan, no API calls
    python scripts/run_nvidia_v1.1.py --dry-run

    # Full sweep (set BEDROCK_API_KEY first)
    BEDROCK_API_KEY=$(cat ~/.aws/bedrock_api_key) python scripts/run_nvidia_v1.1.py

    # Resume interrupted run (safe to re-run — completed cells skipped)
    BEDROCK_API_KEY=$(cat ~/.aws/bedrock_api_key) python scripts/run_nvidia_v1.1.py
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import click

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from refusalbench.council import _CONTENT_FILTERED, aggregate
from refusalbench.judges.base import Judgment, JudgmentError
from refusalbench.judges.llm_judge import LLMJudge, build_judges_from_config
from refusalbench.providers.bedrock import BedrockProvider

# ── Constants ─────────────────────────────────────────────────────────────────

MODEL_ID       = "nvidia.nemotron-super-3-120b"
COUNCIL_JSON   = _REPO_ROOT / "benchmark" / "council" / "v1.1-nvidia.json"
PROMPTS_DIR    = _REPO_ROOT / "benchmark" / "prompts" / "v1.0"
SYSTEM_PROMPT_PATH = _REPO_ROOT / "benchmark" / "prompts" / "system" / "sweep_v1.0.txt"
OUTPUT_CSV     = _REPO_ROOT / "results" / "snapshots" / "2026-05" / "council" / "adjudicated_v1.1_nvidia.csv"

EVAL_CONCURRENCY = 6   # burst test showed 6 concurrent at ~900ms each, no throttling
JUDGE_CONCURRENCY = 3  # 3 council slots × 2 judges = 6 max judge calls in flight
N_TRIALS   = 5
SEED       = 42
MAX_TOKENS = 2048
TEMPERATURE = 0.7

# Judge column names (2-judge council)
_JUDGE_COLUMNS: dict[str, str] = {
    "ai21_jamba":   "judge_ai21_label",
    "meta_llama31": "judge_meta_label",
}

# Output schema — matches adjudicated.csv plus snapshot_version
_FIELDNAMES = [
    "prompt_id", "model", "trial_idx",
    "modal_compliance", "modal_reason",
    "compliance_agreement", "reason_agreement",
    "any_parse_failed", "flagged_for_spot_check",
    "subdomain", "tier",
    "snapshot_version",
    # audit columns
    "judge_ai21_label", "judge_meta_label",
    "response_text", "latency_ms",
]

# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text().strip()


def _load_prompts() -> list[dict[str, str]]:
    """Return [{prompt_id, prompt_text, subdomain, tier}, ...] for all 141 prompts."""
    records: list[dict[str, str]] = []
    for tier_dir in sorted(PROMPTS_DIR.iterdir()):
        if not tier_dir.is_dir():
            continue
        tier = tier_dir.name  # benign / borderline / dual_use
        for path in sorted(tier_dir.glob("*.json")):
            with path.open() as f:
                data = json.load(f)
            prompt_text = data.get("prompt") or data.get("text") or ""
            subdomain = data.get("subdomain") or data.get("domain") or ""
            if not subdomain:
                # infer from prompt_id prefix
                subdomain = path.stem.rsplit("_", 2)[0]
            records.append({
                "prompt_id": path.stem,
                "prompt_text": prompt_text,
                "subdomain": subdomain,
                "tier": tier,
            })
    return records


def _load_completed(output_path: Path) -> set[tuple[str, int]]:
    """Return completed (prompt_id, trial_idx) pairs."""
    completed: set[tuple[str, int]] = set()
    if not output_path.exists():
        return completed
    with output_path.open(newline="") as f:
        for row in csv.DictReader(f):
            try:
                completed.add((row["prompt_id"], int(row["trial_idx"])))
            except (KeyError, ValueError):
                continue
    return completed


def _append_row(output_path: Path, row: dict[str, Any]) -> None:
    write_header = not output_path.exists()
    with output_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(row)

# ── Core async helpers ─────────────────────────────────────────────────────────

async def _eval_one(
    provider: BedrockProvider,
    system: str,
    prompt_text: str,
) -> tuple[str, int]:
    t0 = time.monotonic()
    response = await provider.complete(
        model=MODEL_ID,
        system=system,
        user=prompt_text,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    latency = int((time.monotonic() - t0) * 1000)
    return response, latency


async def _judge_with_semaphore(
    semaphore: asyncio.Semaphore,
    judges: list[LLMJudge],
    prompt_id: str,
    prompt_text: str,
    response_text: str,
) -> tuple[dict[str, str], str, str, float, float, bool, bool]:
    """Run 2-judge council. Returns (labels, modal_compliance, modal_reason,
    compliance_agreement, reason_agreement, any_parse_failed, flagged)."""
    if response_text == _CONTENT_FILTERED:
        labels = {j.judge_id: "direct_refusal" for j in judges}
        return labels, "direct_refusal", "safety_policy", 1.0, 1.0, False, False

    async with semaphore:
        tasks = [j.judge(prompt_id, prompt_text, response_text) for j in judges]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    judgments: list[Judgment] = []
    labels: dict[str, str] = {}
    for judge, result in zip(judges, results):
        if isinstance(result, (JudgmentError, Exception)):
            labels[judge.judge_id] = "non_responsive"
            judgments.append(Judgment(
                judge_id=judge.judge_id, prompt_id=prompt_id,
                compliance="non_responsive", reason="other",
                raw_output="", parse_failed=True,
            ))
        else:
            labels[judge.judge_id] = result.compliance
            judgments.append(result)

    agg = aggregate(judgments)
    return (
        labels,
        agg.modal_compliance,
        agg.modal_reason,
        agg.compliance_agreement,
        agg.reason_agreement,
        agg.any_parse_failed,
        agg.flagged_for_spot_check,
    )

# ── Main sweep ────────────────────────────────────────────────────────────────

async def run_sweep(*, dry_run: bool = False) -> int:
    system_prompt = _load_system_prompt()
    prompts = _load_prompts()
    completed = _load_completed(OUTPUT_CSV)

    total_planned = len(prompts) * N_TRIALS
    already_done  = len(completed)
    remaining     = total_planned - already_done

    if dry_run:
        click.echo("── Nemotron v1.1 Panel Sweep — DRY RUN ──")
        click.echo(f"  Model:     {MODEL_ID}")
        click.echo(f"  Prompts:   {len(prompts)} (benign/borderline/dual_use)")
        click.echo(f"  Trials:    {N_TRIALS} per prompt")
        click.echo(f"  Total:     {total_planned} eval calls")
        click.echo(f"  Completed: {already_done}")
        click.echo(f"  Remaining: {remaining}")
        click.echo(f"  Council:   {COUNCIL_JSON.name} (AI21 Jamba + Meta Llama 3.1 70B)")
        click.echo(f"  Judge calls at completion: {total_planned * 2:,}")
        click.echo(f"  eval_concurrency={EVAL_CONCURRENCY}, judge_concurrency={JUDGE_CONCURRENCY}")
        click.echo(f"  Output:    {OUTPUT_CSV}")
        return 0

    provider = BedrockProvider()
    judges   = build_judges_from_config(council_path=COUNCIL_JSON)
    judge_semaphore = asyncio.Semaphore(JUDGE_CONCURRENCY)
    eval_semaphore  = asyncio.Semaphore(EVAL_CONCURRENCY)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    new_rows = 0

    async def process_cell(p: dict[str, str], trial_idx: int) -> None:
        nonlocal new_rows
        key = (p["prompt_id"], trial_idx)
        if key in completed:
            return

        async with eval_semaphore:
            response, latency = await _eval_one(provider, system_prompt, p["prompt_text"])

        (labels, modal_compliance, modal_reason,
         comp_agreement, reason_agreement,
         any_parse_failed, flagged) = await _judge_with_semaphore(
            judge_semaphore, judges, p["prompt_id"], p["prompt_text"], response
        )

        row: dict[str, Any] = {
            "prompt_id":           p["prompt_id"],
            "model":               MODEL_ID,
            "trial_idx":           trial_idx,
            "modal_compliance":    modal_compliance,
            "modal_reason":        modal_reason,
            "compliance_agreement": comp_agreement,
            "reason_agreement":    reason_agreement,
            "any_parse_failed":    any_parse_failed,
            "flagged_for_spot_check": flagged,
            "subdomain":           p["subdomain"],
            "tier":                p["tier"],
            "snapshot_version":    "v1.1",
            "judge_ai21_label":    labels.get("ai21_jamba", ""),
            "judge_meta_label":    labels.get("meta_llama31", ""),
            "response_text":       response,
            "latency_ms":          latency,
        }
        _append_row(OUTPUT_CSV, row)
        new_rows += 1

    tasks = [
        process_cell(p, trial_idx)
        for p in prompts
        for trial_idx in range(N_TRIALS)
    ]
    click.echo(f"→ Running {remaining} cells for {MODEL_ID}...", err=True)
    await asyncio.gather(*tasks)
    return new_rows


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--dry-run", is_flag=True, default=False, help="Print plan, no API calls.")
@click.option("--output", default=str(OUTPUT_CSV), show_default=True,
              type=click.Path(), help="Override output CSV path.")
def main(dry_run: bool, output: str) -> None:
    """Run the v1.1 Nemotron 3 Super 120B panel addition sweep.

    \b
    Dry-run first to verify setup:
        python scripts/run_nvidia_v1.1.py --dry-run

    \b
    Full sweep:
        BEDROCK_API_KEY=$(cat ~/.aws/bedrock_api_key) python scripts/run_nvidia_v1.1.py
    """
    global OUTPUT_CSV
    OUTPUT_CSV = Path(output)
    written = asyncio.run(run_sweep(dry_run=dry_run))
    if not dry_run:
        click.echo(f"\nDone. Wrote {written:,} new rows to {output}.")


if __name__ == "__main__":
    main()
