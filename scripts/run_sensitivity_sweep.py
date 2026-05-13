"""Resumption-safe system-prompt sensitivity sweep (v1.1).

5 models × 36 prompts × 4 framings × 5 trials = 3,600 eval calls.
3-judge Bedrock council (Cohere Command R+, AI21 Jamba, NVIDIA Nemotron Super 49B).
All inference on Bedrock — zero OpenRouter cost.

[CONTENT_FILTERED] responses from Claude models are classified directly as
direct_refusal / safety_policy.  This is Anthropic's API-level safety system
surfacing through Bedrock's stop-reason field, not Bedrock infrastructure noise.
See benchmark/config/sweep_models.json anthropic_routing_rationale for full
documentation of this classification decision.

Resumption
----------
Run the script twice on the same output path — it skips completed
(prompt_id, model_id, framing_id, trial_idx) cells automatically.

Usage
-----
    # Dry-run: count pending cells, verify config, no API calls
    python scripts/run_sensitivity_sweep.py --dry-run

    # Full sweep
    python scripts/run_sensitivity_sweep.py

    # Override concurrency for testing
    python scripts/run_sensitivity_sweep.py --eval-concurrency 2 --judge-concurrency 3
"""

from __future__ import annotations

import asyncio
import csv
import json
import time
from pathlib import Path
from typing import Any

import click

from refusalbench.council import _CONTENT_FILTERED, aggregate
from refusalbench.judges.base import Judgment, JudgmentError
from refusalbench.judges.llm_judge import LLMJudge, build_judges_from_config
from refusalbench.providers.bedrock import BedrockProvider

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BUNDLES_CSV = _REPO_ROOT / "benchmark" / "sensitivity_bundles.csv"
_FRAMINGS_JSON = _REPO_ROOT / "benchmark" / "prompts" / "system" / "system-prompts-v1.1.json"
_COUNCIL_JSON = _REPO_ROOT / "benchmark" / "council" / "v1.1-sensitivity.json"
_PROMPTS_DIR = _REPO_ROOT / "benchmark" / "prompts" / "v1.0"
_DEFAULT_OUTPUT = _REPO_ROOT / "results" / "sensitivity_sweep_v1.1.csv"

# ---------------------------------------------------------------------------
# Concurrency defaults — tuned for Bedrock on-demand (us-east-1)
#
# framing_concurrency=4: all 4 framings run in parallel per model
# eval_concurrency (per model, per framing):
#   Claude Opus 4.7 / 4.5   → 4   (content_filtered responses are instant)
#   Mistral Large 3          → 5
#   DeepSeek R1              → 2   (reasoning model, slow + lower quota)
#   Amazon Nova Pro          → 8   (Amazon's own model, generous quota)
# judge_concurrency=3: max concurrent council.categorize() calls across all
#   framings (each categorize fires 3 judge calls → 9 max judge API calls)
# ---------------------------------------------------------------------------

_MODEL_EVAL_CONCURRENCY: dict[str, int] = {
    "us.anthropic.claude-opus-4-7-v1:0": 4,
    "us.anthropic.claude-opus-4-5-v1:0": 4,
    "mistral.mistral-large-3-675b-instruct": 5,
    "us.deepseek.r1-v1:0": 2,
    "us.amazon.nova-pro-v1:0": 8,
}

# R1 max_tokens: 1024 (vs 2048 default) — halves wall-clock for the reasoning
# model without affecting refusal signal (we classify, not evaluate quality).
_R1_MAX_TOKENS = 1024
_DEFAULT_MAX_TOKENS = 2048

# Judge column names keyed by judge_id (order matches v1.1-sensitivity.json)
_JUDGE_COLUMNS: dict[str, str] = {
    "cohere_command_r_plus": "judge_cohere_label",
    "ai21_jamba": "judge_ai21_label",
    "nvidia_nemotron": "judge_nvidia_label",
}

_FIELDNAMES = [
    "prompt_id",
    "model_id",
    "framing_id",
    "trial_idx",
    "run_seed",
    "response_text",
    "latency_ms",
    "judge_cohere_label",
    "judge_ai21_label",
    "judge_nvidia_label",
    "modal_compliance",
    "modal_reason",
    "agreement",
]


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------


def _load_framings() -> list[dict[str, Any]]:
    with _FRAMINGS_JSON.open() as f:
        return json.load(f)["framings"]  # type: ignore[no-any-return]


def _load_bundle_prompt_ids() -> list[str]:
    with _BUNDLES_CSV.open(newline="") as f:
        return [row["prompt_id"] for row in csv.DictReader(f)]


def _load_prompt_texts(prompt_ids: list[str]) -> dict[str, str]:
    """Return {prompt_id: prompt_text} for the 36 bundle prompts."""
    texts: dict[str, str] = {}
    for tier_dir in _PROMPTS_DIR.iterdir():
        if not tier_dir.is_dir():
            continue
        for path in tier_dir.glob("*.json"):
            pid = path.stem
            if pid in prompt_ids:
                with path.open() as f:
                    texts[pid] = json.load(f)["prompt"]
    missing = set(prompt_ids) - texts.keys()
    if missing:
        raise FileNotFoundError(f"Prompt files not found for IDs: {sorted(missing)}")
    return texts


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------


def _load_completed(output_path: Path) -> set[tuple[str, str, str, int]]:
    """Return completed (prompt_id, model_id, framing_id, trial_idx) tuples."""
    completed: set[tuple[str, str, str, int]] = set()
    if not output_path.exists():
        return completed
    with output_path.open(newline="") as f:
        for row in csv.DictReader(f):
            try:
                completed.add((
                    row["prompt_id"],
                    row["model_id"],
                    row["framing_id"],
                    int(row["trial_idx"]),
                ))
            except (KeyError, ValueError):
                continue
    return completed


def _append_row(output_path: Path, row: dict[str, object]) -> None:
    """Append one row. Creates file with header if it doesn't exist."""
    write_header = not output_path.exists()
    with output_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


# ---------------------------------------------------------------------------
# Core async helpers
# ---------------------------------------------------------------------------


async def _eval_one(
    provider: BedrockProvider,
    model_id: str,
    system: str | None,
    prompt_text: str,
    max_tokens: int,
) -> tuple[str, int]:
    """Evaluate one (model, system, prompt) — returns (response_text, latency_ms).

    For P1 (system=None) we pass system="" so BedrockProvider omits the
    system field from the Converse API body entirely.
    """
    t0 = time.monotonic()
    response = await provider.complete(
        model=model_id,
        system=system if system is not None else "",
        user=prompt_text,
        temperature=0.7,
        max_tokens=max_tokens,
    )
    latency = int((time.monotonic() - t0) * 1000)
    return response, latency


async def _categorize_with_semaphore(
    semaphore: asyncio.Semaphore,
    judges: list[LLMJudge],
    prompt_id: str,
    prompt_text: str,
    response_text: str,
) -> tuple[dict[str, str], str, str, bool]:
    """Run council under a global semaphore to cap concurrent judge API calls.

    Returns (judge_labels, modal_compliance, modal_reason, agreement).
    agreement=True when all judges return the same compliance label.

    [CONTENT_FILTERED] responses bypass judges and are recorded as
    direct_refusal / safety_policy with full agreement.
    """
    # Fast path: content-filtered response — no judge calls needed
    if response_text == _CONTENT_FILTERED:
        labels = {j.judge_id: "direct_refusal" for j in judges}
        return labels, "direct_refusal", "safety_policy", True

    async with semaphore:
        # Fire all judges concurrently within the semaphore slot
        tasks = [j.judge(prompt_id, prompt_text, response_text) for j in judges]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    judgments: list[Judgment] = []
    labels: dict[str, str] = {}
    for judge, result in zip(judges, results):
        if isinstance(result, JudgmentError):
            # Hard failure — record non_responsive for this judge slot
            labels[judge.judge_id] = "non_responsive"
            judgments.append(Judgment(
                judge_id=judge.judge_id,
                prompt_id=prompt_id,
                compliance="non_responsive",
                reason="other",
                raw_output="",
                parse_failed=True,
            ))
        elif isinstance(result, Exception):
            labels[judge.judge_id] = "non_responsive"
            judgments.append(Judgment(
                judge_id=judge.judge_id,
                prompt_id=prompt_id,
                compliance="non_responsive",
                reason="other",
                raw_output="",
                parse_failed=True,
            ))
        else:
            labels[judge.judge_id] = result.compliance
            judgments.append(result)

    agg = aggregate(judgments)
    agreement = agg.compliance_agreement == 1.0
    return labels, agg.modal_compliance, agg.modal_reason, agreement


# ---------------------------------------------------------------------------
# Main sweep logic
# ---------------------------------------------------------------------------


async def run_sensitivity_sweep(
    *,
    output_path: Path = _DEFAULT_OUTPUT,
    eval_concurrency_override: int | None = None,
    judge_concurrency: int = 3,
    n_trials: int = 5,
    seed: int = 42,
    dry_run: bool = False,
) -> int:
    """Run the full sensitivity sweep with resumption.

    Parameters
    ----------
    output_path:
        CSV file to write results to. Appended if it exists (resumption).
    eval_concurrency_override:
        If set, overrides per-model eval concurrency for all models.
    judge_concurrency:
        Max concurrent council.categorize() calls across all framings.
        Each call fires 3 judge API calls internally, so actual max
        concurrent judge calls = judge_concurrency × 3.
    n_trials:
        Number of trials per (prompt, model, framing) cell.
    seed:
        Base seed; run_seed = seed + trial_idx.
    dry_run:
        Print plan and exit without making any API calls.

    Returns
    -------
    int
        Number of new rows written.
    """
    framings = _load_framings()
    prompt_ids = _load_bundle_prompt_ids()
    prompt_texts = _load_prompt_texts(prompt_ids)
    completed = _load_completed(output_path)

    models = list(_MODEL_EVAL_CONCURRENCY.keys())
    total_planned = len(models) * len(framings) * len(prompt_ids) * n_trials
    already_done = len(completed)
    remaining = total_planned - already_done

    if dry_run:
        click.echo(f"── Sensitivity Sweep v1.1 — DRY RUN ──")
        click.echo(f"  Output:      {output_path}")
        click.echo(f"  Total cells: {total_planned:,}")
        click.echo(f"  Completed:   {already_done:,}")
        click.echo(f"  Remaining:   {remaining:,}")
        click.echo(f"  Models ({len(models)}):")
        for m in models:
            conc = eval_concurrency_override or _MODEL_EVAL_CONCURRENCY[m]
            mtok = _R1_MAX_TOKENS if "deepseek.r1" in m else _DEFAULT_MAX_TOKENS
            click.echo(f"    {m}  eval_concurrency={conc}  max_tokens={mtok}")
        click.echo(f"  Framings ({len(framings)}): {[f['framing_id'] for f in framings]}")
        click.echo(f"  Prompts: {len(prompt_ids)}")
        click.echo(f"  judge_concurrency={judge_concurrency} "
                   f"(≤{judge_concurrency * 3} concurrent judge API calls)")
        return 0

    # Build shared infrastructure
    provider = BedrockProvider()
    judges = build_judges_from_config(council_path=_COUNCIL_JSON)
    judge_semaphore = asyncio.Semaphore(judge_concurrency)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    new_rows = 0

    for model_id in models:
        eval_conc = eval_concurrency_override or _MODEL_EVAL_CONCURRENCY[model_id]
        max_tokens = _R1_MAX_TOKENS if "deepseek.r1" in model_id else _DEFAULT_MAX_TOKENS
        click.echo(
            f"\n→ {model_id}  eval_concurrency={eval_conc}  max_tokens={max_tokens}",
            err=True,
        )

        # Run all 4 framings concurrently for this model
        async def process_framing(
            framing: dict[str, Any],
            _model_id: str = model_id,
            _eval_conc: int = eval_conc,
            _max_tokens: int = max_tokens,
        ) -> None:
            nonlocal new_rows
            framing_id: str = framing["framing_id"]
            system_text: str | None = framing["text"]  # None → P1 (omit system)

            cell_semaphore = asyncio.Semaphore(_eval_conc)

            async def process_cell(pid: str, trial_idx: int) -> None:
                nonlocal new_rows
                if (pid, _model_id, framing_id, trial_idx) in completed:
                    return

                async with cell_semaphore:
                    response, latency = await _eval_one(
                        provider, _model_id, system_text, prompt_texts[pid], _max_tokens
                    )
                    judge_labels, modal_compliance, modal_reason, agreement = (
                        await _categorize_with_semaphore(
                            judge_semaphore, judges, pid, prompt_texts[pid], response
                        )
                    )

                row: dict[str, object] = {
                    "prompt_id": pid,
                    "model_id": _model_id,
                    "framing_id": framing_id,
                    "trial_idx": trial_idx,
                    "run_seed": seed + trial_idx,
                    "response_text": response,
                    "latency_ms": latency,
                    "judge_cohere_label": judge_labels.get("cohere_command_r_plus", ""),
                    "judge_ai21_label": judge_labels.get("ai21_jamba", ""),
                    "judge_nvidia_label": judge_labels.get("nvidia_nemotron", ""),
                    "modal_compliance": modal_compliance,
                    "modal_reason": modal_reason,
                    "agreement": agreement,
                }
                _append_row(output_path, row)
                new_rows += 1

            tasks = [
                process_cell(pid, trial_idx)
                for pid in prompt_ids
                for trial_idx in range(n_trials)
            ]
            await asyncio.gather(*tasks)

        framing_tasks = [process_framing(f) for f in framings]
        await asyncio.gather(*framing_tasks)
        click.echo(f"  ✓ done", err=True)

    return new_rows


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--output",
    default=str(_DEFAULT_OUTPUT),
    show_default=True,
    type=click.Path(),
    help="Output CSV path.",
)
@click.option(
    "--eval-concurrency",
    default=None,
    type=int,
    help=(
        "Override per-model eval concurrency for all models. "
        "Default: per-model values (Claude/Mistral=4-5, R1=2, Nova=8)."
    ),
)
@click.option(
    "--judge-concurrency",
    default=3,
    show_default=True,
    type=int,
    help=(
        "Max concurrent council evaluations across all framings. "
        "Each evaluation fires 3 judge calls, so actual max judge API calls "
        "= judge-concurrency × 3. Default 3 → ≤9 judge calls in flight."
    ),
)
@click.option("--n-trials", default=5, show_default=True, type=int)
@click.option("--seed", default=42, show_default=True, type=int)
@click.option("--dry-run", is_flag=True, default=False, help="Print plan and exit.")
@click.option("--aws-region", default=None, help="Override AWS region for Bedrock.")
def main(
    output: str,
    eval_concurrency: int | None,
    judge_concurrency: int,
    n_trials: int,
    seed: int,
    dry_run: bool,
    aws_region: str | None,
) -> None:
    """Run the RefusalBench v1.1 system-prompt sensitivity sweep.

    All inference on Bedrock. [CONTENT_FILTERED] responses from Claude models
    are classified as direct_refusal/safety_policy (Anthropic API-level refusal).

    \b
    Example — dry run to check pending cells:
        python scripts/run_sensitivity_sweep.py --dry-run

    \b
    Example — full sweep:
        python scripts/run_sensitivity_sweep.py

    \b
    Example — reduced concurrency if hitting 429s:
        python scripts/run_sensitivity_sweep.py --eval-concurrency 2 --judge-concurrency 2
    """
    if aws_region:
        import os
        os.environ.setdefault("AWS_DEFAULT_REGION", aws_region)

    written = asyncio.run(
        run_sensitivity_sweep(
            output_path=Path(output),
            eval_concurrency_override=eval_concurrency,
            judge_concurrency=judge_concurrency,
            n_trials=n_trials,
            seed=seed,
            dry_run=dry_run,
        )
    )
    if not dry_run:
        click.echo(f"\nDone. Wrote {written:,} new rows to {output}.")


if __name__ == "__main__":
    main()
